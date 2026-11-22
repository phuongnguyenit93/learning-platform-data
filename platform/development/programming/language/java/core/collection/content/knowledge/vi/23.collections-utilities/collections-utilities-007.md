# addAll và chuyển các đối số thành phần tử collection

## 1. Từ nhiều đối số đến một collection đang có

Giả sử một danh sách đã có phần tử ban đầu và cần bổ sung ba tên. Có thể gọi `add` ba lần, hoặc dùng `Collections.addAll(destination, first, second, third)` để diễn đạt cùng nhu cầu thêm nhiều phần tử.

Phương thức này nhận **collection đích đã tồn tại**. Nó không tự tạo List mới, không xóa dữ liệu đích cũ và không trả về collection đã được điền. Những đối số sau đích là các phần tử được đề nghị thêm. Kết quả trả về là boolean cho biết collection đích có thay đổi do lời gọi hay không.

Cần tách hai vai trò:

- **Cách cung cấp dữ liệu:** truyền từng đối số hoặc một mảng phù hợp với tham số varargs.
- **Cách lưu dữ liệu:** List, Set hoặc loại Collection cụ thể quyết định quyền thêm, phần tử trùng, thứ tự và ràng buộc giá trị.

Vì vậy, cùng một dãy đối số có thể làm List tăng kích thước theo số lần xuất hiện nhưng chỉ bổ sung một số giá trị mới vào Set. `Collections.addAll` không biến mọi collection thành List và không ghi đè quy tắc của đích.

Từ “chuyển các đối số thành phần tử” cũng cần đọc đúng mức: phương thức thêm các giá trị hoặc tham chiếu đối số vào đích. Nó không tự trải đệ quy một cấu trúc lồng nhau và không tự sao chép sâu đối tượng phần tử.

Bài học đi từ chữ ký, phép thêm cơ bản và giá trị boolean đến varargs với mảng, null, quyền sửa và các lỗi thường gặp. Người học cần biết cách tạo ArrayList/Set, phương thức add và mảng Java. Mọi chương trình dưới đây là tệp độc lập, biên dịch và chạy bằng Java 17 theo lệnh ghi kèm.

## 2. Đọc chữ ký Collections.addAll

Chữ ký khái quát là:

`static <T> boolean addAll(Collection<? super T> destination, T... elements)`

| Thành phần | Ý nghĩa |
| --- | --- |
| `static` | Gọi qua lớp tiện ích Collections |
| `<T>` | Kiểu phần tử mà lời gọi đang thêm |
| `Collection<? super T>` | Đích có thể nhận T hoặc kiểu cha phù hợp của T |
| `T... elements` | Tham số số lượng biến đổi, còn gọi là varargs |
| `boolean` | Có thay đổi collection do lời gọi hay không |

Phần `? super T` giúp một đích có kiểu phần tử rộng hơn tiếp nhận các đối số có kiểu hẹp hơn. Ví dụ, `List<Number>` có thể nhận Integer, Long và Double vì chúng đều là Number. Không cần biến đích thành kiểu thô để thêm các giá trị phù hợp đó.

Kiểu rộng không có nghĩa mọi giá trị đều hợp lệ. `List<Integer>` không trở thành nơi chứa String chỉ vì phương thức là generic. Kiểm tra kiểu ở lúc biên dịch vẫn giúp ngăn việc thêm không tương thích; một collection cụ thể còn có thể có ràng buộc ở thời điểm chạy.

Varargs cho phép gọi với không phần tử, một phần tử hoặc nhiều phần tử. Khi truyền từng đối số, Java có cơ chế đóng gói chúng thành mảng cho tham số cuối. Khi đã có một mảng phù hợp, có thể truyền chính mảng ấy làm tham số. Điều quyết định các phần tử được thêm là **kiểu của lời gọi và hình dạng mảng**, không phải mong muốn tự động trải mọi dữ liệu.

Phương thức có từ Java 5. Trong bài dùng JDK 17 để các ví dụ có môi trường thống nhất. Hợp đồng gốc: [Collections.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#addAll(java.util.Collection,T...)).

## 3. Thí nghiệm thêm các đối số vào List

Lưu thành `AddAllBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class AddAllBasicsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("seed"));
        boolean changed = Collections.addAll(names, "An", "Binh", "An");
        System.out.println("changed=" + changed);
        System.out.println("names=" + names);
        System.out.println("size=" + names.size());

        boolean emptyArguments = Collections.addAll(names);
        System.out.println("emptyArguments=" + emptyArguments);

        List<Number> numbers = new ArrayList<>();
        Collections.addAll(numbers, 1, 2L, 3.5);
        System.out.println("numbers=" + numbers);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AddAllBasicsDemo.java
java AddAllBasicsDemo
```

Stdout:

```text
changed=true
names=[seed, An, Binh, An]
size=4
emptyArguments=false
numbers=[1, 2, 3.5]
```

List đã chứa seed trước lời gọi. Ba đối số được bổ sung vào ArrayList theo thứ tự đã truyền, gồm hai lần xuất hiện của An. Collection cũ không bị thay bằng một đối tượng mới và phần tử seed không bị xóa.

Biến `changed` là true vì List đã có thêm phần tử. Nó không mang giá trị bốn hay ba; số phần tử cần đọc bằng `size()` hoặc tính riêng theo mục tiêu của chương trình.

Ca không truyền thêm phần tử trả false trên List có thể sửa trong thí nghiệm: không có phần tử nào được bổ sung nên đích không thay đổi. Điều này khác với truyền một đối số null, vốn có thể là một phần tử thực nếu đích cho phép.

Các số `1`, `2L` và `3.5` được đưa vào `List<Number>`. Java có thể đóng gói các giá trị nguyên thủy đơn lẻ thành kiểu bao tương ứng khi lời gọi yêu cầu. Chuỗi in không có nghĩa mọi phần tử đã bị ép thành cùng kiểu số thực; đích Number có thể chứa nhiều kiểu số con.

Nếu cần dùng ngay dữ liệu đã thêm, đọc chính biến `names` hoặc `numbers`. Gán kết quả của Collections.addAll vào một biến List là sai ý nghĩa kiểu trả về.

## 4. Boolean và phần tử trùng phụ thuộc collection đích

Đối với List cho phép thêm, việc thêm lại một giá trị thường tạo thêm một lần xuất hiện. Đối với Set, một phần tử đã có có thể không làm thay đổi tập hợp. Vì vậy, true không có nghĩa “mọi đối số đều trở thành phần tử mới”, còn false không nhất thiết là lỗi.

Lưu thành `AddAllDestinationsDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class AddAllDestinationsDemo {
    public static void main(String[] args) {
        Set<String> ordered = new LinkedHashSet<>(List.of("A"));
        boolean first = Collections.addAll(ordered, "A", "B", "B");
        boolean repeated = Collections.addAll(ordered, "A", "B");
        System.out.println("first=" + first);
        System.out.println("repeated=" + repeated);
        System.out.println("ordered=" + ordered);
        System.out.println("size=" + ordered.size());

        Set<String> sorted = new TreeSet<>();
        Collections.addAll(sorted, "C", "A", "B");
        System.out.println("sorted=" + sorted);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AddAllDestinationsDemo.java
java AddAllDestinationsDemo
```

Stdout:

```text
first=true
repeated=false
ordered=[A, B]
size=2
sorted=[A, B, C]
```

LinkedHashSet ban đầu đã có A. Lần thêm đầu nhận A, B, B: chỉ B tạo giá trị mới, nhưng cả lời gọi vẫn trả true vì tập hợp có thay đổi. Lần thêm tiếp chỉ nhận A và B vốn đã có nên trả false.

Kích thước Set bằng hai, không bằng tổng số đối số từng được truyền. Nếu cần lưu số lần một giá trị xuất hiện, Set không biểu diễn đủ dữ liệu ấy.

Thứ tự in của `ordered` đến từ hợp đồng LinkedHashSet giữ thứ tự chèn. Việc đề nghị thêm lại phần tử đã có không chuyển nó xuống cuối trong kiểu này. Kết quả `sorted` lại đến từ TreeSet sắp xếp theo thứ tự tự nhiên của String, dù lời gọi truyền C, A, B.

Không lấy thứ tự đối số làm lời hứa về thứ tự duyệt của mọi Collection. Chọn đích theo nhu cầu dữ liệu: List giữ chuỗi các lần xuất hiện; Set quản lý giá trị phân biệt; các loại Set cụ thể có hoặc không có cam kết thứ tự riêng.

Tài liệu đích dùng trong ví dụ: [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) và [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html). Với phần tử tự định nghĩa, cần giữ quy tắc bằng nhau hoặc so sánh ổn định theo hợp đồng của cấu trúc đã chọn.

## 5. Phân biệt Collections.addAll với collection.addAll

Hai cách viết cùng tên nhận hình dạng đầu vào khác nhau:

| Cách gọi | Đối tượng nhận dữ liệu | Dữ liệu được đưa vào | Giá trị trả về |
| --- | --- | --- | --- |
| `Collections.addAll(target, a, b, c)` | Tham số target | Các đối số phần tử hoặc mảng phù hợp | Boolean có thay đổi |
| `target.addAll(source)` | Chính target | Một Collection nguồn | Boolean có thay đổi |

Nếu dữ liệu đã là một Collection, phương thức của đích diễn đạt trực tiếp việc thêm các phần tử của nguồn. Nếu dữ liệu là vài giá trị rời hoặc một mảng tham chiếu phù hợp, tiện ích Collections thường giúp lời gọi ngắn gọn.

Đừng truyền một List làm đối số phần tử cho Collections.addAll rồi mặc định phương thức sẽ mở List đó ra. Nếu kiểu đích cho phép, List ấy có thể là **một phần tử lồng**. Tiện ích không coi mọi đối tượng triển khai Iterable là dãy cần tự trải.

Tương tự, Map không trực tiếp là Collection để dùng làm đích của chữ ký này. Cần đọc đúng kiểu dữ liệu và thao tác ánh xạ mà API đang yêu cầu, thay vì dựa trên từ “collection” theo nghĩa nói chung.

`Collection.addAll` không làm nguồn trở thành dữ liệu độc lập: các phần tử là đối tượng vẫn có thể được dùng chung tham chiếu. Cả hai cách thêm đều không là thao tác sao chép sâu chỉ vì có chữ All.

Nếu cân nhắc hiệu năng, không mặc định rằng cách viết nào luôn nhanh hơn trên mọi đích. Một số collection có cách thêm hàng loạt riêng; số phần tử và chi phí thêm/so sánh cũng ảnh hưởng. Chọn cách gọi đúng với hình dạng đầu vào trước, rồi đo khi thực sự có đường chạy cần tối ưu.

Xem chữ ký nhận Collection nguồn trong [Collection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)).

## 6. Mảng truyền vào varargs: trải một tầng theo kiểu phù hợp

Một mảng String phù hợp với tham số `T...` khi T là String. Khi truyền mảng ấy, tiện ích lấy các phần tử String của mảng để thêm vào collection đích. Nó không thêm chính mảng như một phần tử String.

Nhưng nếu T là `String[]`, thì một phần tử là cả mảng String. Collection đích khi ấy có dạng `List<String[]>`; tham số varargs tương ứng ở một tầng mảng cao hơn. Phải đọc kiểu phần tử trước khi dự đoán số phần tử được thêm.

Lưu thành `ArrayVarargsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ArrayVarargsDemo {
    public static void main(String[] args) {
        String[] names = {"An", "Binh"};
        List<String> flat = new ArrayList<>();
        Collections.addAll(flat, names);

        List<String[]> groups = new ArrayList<>();
        Collections.<String[]>addAll(groups, names);
        System.out.println("flat=" + flat);
        System.out.println("groupCount=" + groups.size());
        System.out.println("sameArray=" + (groups.get(0) == names));
        System.out.println("group=" + Arrays.toString(groups.get(0)));

        names[0] = "Changed";
        System.out.println("flatAfterArrayEdit=" + flat);
        System.out.println("groupAfterArrayEdit=" + Arrays.toString(groups.get(0)));

        int[] raw = {1, 2, 3};
        List<int[]> batches = new ArrayList<>();
        Collections.addAll(batches, raw);
        System.out.println("batchCount=" + batches.size());
        System.out.println("batch=" + Arrays.toString(batches.get(0)));

        List<Integer> boxed = new ArrayList<>();
        for (int value : raw) {
            boxed.add(value);
        }
        System.out.println("boxed=" + boxed);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ArrayVarargsDemo.java
java ArrayVarargsDemo
```

Stdout:

```text
flat=[An, Binh]
groupCount=1
sameArray=true
group=[An, Binh]
flatAfterArrayEdit=[An, Binh]
groupAfterArrayEdit=[Changed, Binh]
batchCount=1
batch=[1, 2, 3]
boxed=[1, 2, 3]
```

Có ba hình dạng dữ liệu khác nhau trong chương trình:

| Đích | Đối số được thêm | Số phần tử mới trong ví dụ |
| --- | --- | --- |
| `List<String>` | Các String trong mảng names | Hai |
| `List<String[]>` | Cả mảng names như một phần tử | Một |
| `List<int[]>` | Cả mảng raw như một phần tử | Một |

Lời gọi `Collections.<String[]>addAll(groups, names)` ghi rõ kiểu T là `String[]`. Đó là cách biểu đạt chủ đích “collection chứa các mảng”. Nó không là thao tác chuyển một nhóm String thành một String duy nhất.

Dòng `sameArray=true` cho thấy phần tử trong groups là chính mảng names. Khi thay phần tử đầu của mảng, nội dung quan sát qua groups thay đổi. Còn flat vẫn giữ An và Binh vì nó đã nhận các tham chiếu String từ các ô mảng tại lúc thêm; thay tham chiếu trong ô mảng về sau không thay vị trí List đã có.

Sự độc lập của flat với việc gán lại ô mảng không chứng minh sao chép sâu phần tử. Nếu mảng chứa các đối tượng có thể sửa, List nhận các đối tượng ấy vẫn có thể quan sát thay đổi trạng thái của chúng.

### Vì sao int[] không tự thành nhiều Integer?

Một mảng `int[]` là một đối tượng mảng, nhưng nó không là `Integer[]`. Cơ chế đóng gói các giá trị int đơn lẻ không tự chuyển cả `int[]` thành mảng các Integer.

Trong chương trình, phần tử của batches có kiểu `int[]`, nên việc thêm một mảng raw làm kích thước batches bằng một. Để có `List<Integer>` chứa từng số, vòng lặp cuối lấy từng int và thêm giá trị ấy; tại từng lần thêm, Java mới áp dụng việc đóng gói phù hợp.

Không cố giải quyết bằng một phép ép kiểu mảng không hợp lệ. Quyết định muốn lưu **từng số** hay **từng mảng số** trước, rồi chọn kiểu collection và quá trình chuyển đổi tương ứng.

Quy tắc gọi phương thức có số lượng đối số biến đổi và việc chuẩn bị mảng tham số được mô tả trong [JLS 17, đánh giá đối số của lời gọi phương thức](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2).

## 7. Không có đối số, một phần tử null và mảng null

Ba tình huống này khác nhau:

- Không có phần tử để thêm: phần varargs biểu diễn một dãy rỗng.
- Có một đối số phần tử null: dãy có một vị trí, vị trí ấy chứa null.
- Mảng varargs là null: không có đối tượng mảng hợp lệ để lấy dãy phần tử.

Chính sách null còn phụ thuộc collection đích. ArrayList cho phép phần tử null; một số collection khác từ chối. Varargs không tự biến null thành chuỗi rỗng, không bỏ qua null và không thay quy tắc của đích.

Lưu thành `NullVarargsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class NullVarargsDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>();
        boolean changed = Collections.addAll(values, (String) null);
        System.out.println("oneNullChanged=" + changed);
        System.out.println("values=" + values);
        System.out.println("size=" + values.size());

        try {
            Collections.addAll(values, (String[]) null);
        } catch (NullPointerException e) {
            System.out.println("nullArray=NullPointerException");
        }

        try {
            Collections.<String>addAll(null, "A");
        } catch (NullPointerException e) {
            System.out.println("nullDestination=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NullVarargsDemo.java
java NullVarargsDemo
```

Stdout:

```text
oneNullChanged=true
values=[null]
size=1
nullArray=NullPointerException
nullDestination=NullPointerException
```

Ép kiểu `(String) null` diễn đạt một phần tử String có giá trị null. Với ArrayList trong ví dụ, phần tử đó được thêm, kích thước bằng một và boolean là true.

Ép kiểu `(String[]) null` lại diễn đạt chính mảng phần tử là null. Lời gọi phát sinh ngoại lệ; đây không phải cách yêu cầu thêm một phần tử null.

Ca cuối kiểm tra đích null với một phần tử thực sự cần thêm. Một collection đích hợp lệ phải tồn tại trước khi dùng tiện ích. Không dùng những đường thực thi không có tác dụng để suy đoán rằng null là một đích được API hỗ trợ.

Tránh viết một đối số null không ghi rõ kiểu khi mục tiêu là phân biệt hai ý nghĩa trên. Trong ngữ cảnh varargs, null trần có thể được hiểu theo kiểu mảng phù hợp và dễ dẫn đến lời gọi khác với ý định “thêm một phần tử null”. Việc ghi kiểu rõ trong thí nghiệm giúp quan sát chính xác tình huống cần kiểm tra.

## 8. Đích phải hỗ trợ thêm và đáp ứng ràng buộc phần tử

Collections.addAll cần khả năng **thêm** vào collection đích. Một List có thể cho thay phần tử nhưng không cho tăng kích thước; điều đó không đáp ứng yêu cầu bổ sung phần tử mới.

List từ Arrays.asList có kích thước cố định theo mảng nền. List từ List.of không cho sửa phần chứa. Trong hai trường hợp, lời gọi cố thêm phần tử mới đều bị chặn, nhưng nguyên nhân khả năng của chúng không hoàn toàn giống nhau.

Ngoài quyền thêm, đích còn có thể từ chối null hoặc một giá trị không đáp ứng điều kiện của nó. Một lỗi trong lúc thêm hàng loạt không mang theo lời hứa rằng mọi phần tử trước đó sẽ được hoàn tác.

Lưu thành `AddAllLimitsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.List;

public class AddAllLimitsDemo {
    public static void main(String[] args) {
        List<String> fixed = Arrays.asList("base");
        try {
            Collections.addAll(fixed, "new");
        } catch (UnsupportedOperationException e) {
            System.out.println("fixed=UnsupportedOperationException");
        }

        List<String> readOnly = List.of("base");
        try {
            Collections.addAll(readOnly, "new");
        } catch (UnsupportedOperationException e) {
            System.out.println("readOnly=UnsupportedOperationException");
        }

        Deque<String> queue = new ArrayDeque<>();
        queue.add("seed");
        try {
            Collections.addAll(queue, "first", null, "last");
        } catch (NullPointerException e) {
            System.out.println("nullElement=NullPointerException");
        }
        System.out.println("queueAfterFailure=" + queue);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AddAllLimitsDemo.java
java AddAllLimitsDemo
```

Stdout:

```text
fixed=UnsupportedOperationException
readOnly=UnsupportedOperationException
nullElement=NullPointerException
queueAfterFailure=[seed, first]
```

Hai ca đầu chủ động thêm một phần tử mới nên chứng minh trực tiếp việc đích không hỗ trợ thao tác cần dùng. Không nên thử lời gọi với không đối số rồi xem kết quả đó là bằng chứng rằng đích có thể thêm phần tử.

Ở ca ArrayDeque, dữ liệu ban đầu là seed. Trong lần chạy JDK 17 này, first đã được thêm trước khi việc gặp null gây ngoại lệ; last không được thêm. Collection sau lỗi còn `[seed, first]`.

Điều rút ra là không có cam kết hoàn tác toàn bộ cho lời gọi tiện ích. Không viết nghiệp vụ dựa vào giả định “có ngoại lệ thì đích chắc chắn như cũ”, cũng không phụ thuộc một tiền tố cập nhật cụ thể để điều khiển chương trình.

Nếu yêu cầu là tiếp nhận trọn một nhóm giá trị hoặc từ chối cả nhóm, cần một quy trình phù hợp: kiểm tra và chuẩn bị dữ liệu trước khi công bố, chọn đích đáp ứng mọi ràng buộc, và xử lý cập nhật theo hợp đồng của ứng dụng. Tạo một collection tạm chỉ giải quyết được phần chuẩn bị; nó không tự làm thao tác lên collection dùng chung thành một giao dịch.

ArrayDeque từ chối null theo [hợp đồng ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html). Khả năng cố định kích thước và liên hệ với mảng được mô tả tại [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 9. Thêm vào đích hay tạo một collection từ đối số?

Khi bắt đầu với vài đối số, có nhiều cách diễn đạt nhưng chúng không có cùng vai trò.

| Nhu cầu | Công cụ thường phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Bổ sung vào collection đang có | `Collections.addAll(target, ...)` | Thay đổi target; trả boolean |
| Bổ sung từ Collection nguồn | `target.addAll(source)` | Nguồn phải là Collection phù hợp |
| Lấy List theo các giá trị hoặc mảng tham chiếu | `Arrays.asList(...)` | Kích thước cố định; có quan hệ với mảng |
| Tạo List chỉ đọc từ các phần tử | `List.of(...)` | Không cho sửa phần chứa; không nhận null |
| Tạo ArrayList riêng từ một Collection | Constructor nhận Collection | Phần chứa có thể sửa; phần tử vẫn có thể dùng chung |

Nếu mục tiêu là tạo một List có thể tiếp tục thêm/xóa, có thể tạo ArrayList rồi dùng Collections.addAll để đưa những giá trị ban đầu vào. Đừng nhầm boolean của tiện ích với kết quả của một phương thức tạo List.

Nếu dùng Arrays.asList để chuẩn bị List, cần nhớ đó không phải một ArrayList độc lập có thể tăng kích thước. Việc tên lớp tiện ích gần nhau không làm hai hợp đồng giống nhau.

Nếu chọn List.of làm kết quả chỉ đọc, chính sách null cũng thay đổi so với một ArrayList nhận phần tử null. Chọn công cụ theo yêu cầu dữ liệu, không chỉ theo số dòng mã.

Với mảng nguyên thủy, vấn đề “mảng là một phần tử hay từng giá trị là phần tử” vẫn cần xét ở các API generic nhận varargs. Đổi từ Collections.addAll sang một phương thức khác có tên tạo List không tự chuyển `int[]` thành nhiều Integer.

Các đặc điểm của List chỉ đọc do factory cung cấp được mô tả trong [List: Unmodifiable Lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable).

## 10. Đọc lời gọi theo đích, kiểu phần tử và kết quả

Khi gặp một lời gọi Collections.addAll, có thể phân tích theo ba bước.

**Bước một: xác định đích.** Đích đã tồn tại chưa, có hỗ trợ add không, có chấp nhận null không và dùng quy tắc nào để nhận diện phần tử trùng? Chính đối tượng đích quyết định cách phần tử trở thành dữ liệu trong collection.

**Bước hai: xác định một phần tử có kiểu gì.** Trong `List<String>`, một phần tử là một chuỗi. Trong `List<String[]>`, một phần tử là cả một mảng chuỗi. Với một List chứa các List, truyền một List có thể là thêm một phần tử lồng; không có cơ chế tự trải mọi tầng.

**Bước ba: đọc boolean theo thay đổi của đích.** True nghĩa là có thay đổi, không cho biết đã thêm được bao nhiêu phần tử mới. Một vài đối số đã có trong Set không ngăn các đối số mới khác được thêm. Khi lời gọi hoàn tất bình thường, phương thức đã xử lý nhóm phần tử theo hợp đồng, không dùng lần thay đổi đầu tiên để bỏ qua phần còn lại.

Đối với dữ liệu lỗi, phải xét riêng việc lời gọi chưa hoàn tất. Ngoại lệ không mang một kết quả boolean hợp lệ về cho biến nhận, nhưng điều đó cũng không hứa rằng đích chưa bị thay đổi.

Cuối cùng, nhận biết quan hệ tham chiếu. Thêm một đối tượng có thể sửa vào collection không chuyển riêng toàn bộ trạng thái của đối tượng đó cho collection. Bên ngoài có thể vẫn giữ tham chiếu. Chương trình mảng lồng đã cho thấy cùng một mảng được quan sát qua cả biến nguồn và phần tử đích.

Nếu collection được dùng chung giữa nhiều luồng, tiện ích này không thay thế chính sách phối hợp truy cập của đích. Cần phân biệt việc một lệnh add riêng lẻ được một loại collection hỗ trợ với yêu cầu cập nhật cả nhóm như một bước nghiệp vụ thống nhất.

## 11. Lỗi phổ biến và cách xác định nguyên nhân

| Hiểu nhầm hoặc lỗi | Cách đọc đúng |
| --- | --- |
| Gán kết quả Collections.addAll cho một biến List | Kết quả là boolean; đọc collection đã truyền để lấy dữ liệu |
| Tưởng lời gọi xóa dữ liệu cũ rồi điền lại | Tiện ích bổ sung theo quyền add của đích |
| Mong số phần tử Set tăng đúng bằng số đối số | Đối số trùng có thể không tạo giá trị mới |
| Cho rằng false luôn báo thêm thất bại | Đích có thể không đổi vì mọi giá trị đã có hoặc không có phần tử để thêm |
| Truyền một List rồi mong tự trải thành nhiều phần tử | Dùng phương thức nhận Collection nguồn nếu mục tiêu là lấy các phần tử của List đó |
| Truyền int[] rồi mong nhiều Integer | Mảng nguyên thủy không tự chuyển thành mảng kiểu bao; cần chuyển từng giá trị |
| Dùng null mà không phân biệt phần tử và mảng | Ghi rõ kiểu và ý định; chính sách null còn phụ thuộc đích |
| Thêm vào Arrays.asList vì nó cho phép set | Quyền thay phần tử không đồng nghĩa quyền tăng kích thước |
| Nghĩ gặp ngoại lệ thì đích chắc chắn như cũ | Không có cam kết hoàn tác chung; cần quy trình tiếp nhận phù hợp |
| Nghĩ thêm đối tượng vào collection là sao chép sâu | Đích có thể giữ chính tham chiếu đối tượng đầu vào |

Khi kiểm tra một ca khó, đừng chỉ in collection. In thêm `size()`, kiểu phần tử đã khai báo, boolean trả về và nội dung mảng bằng `Arrays.toString` khi cần. Với collection chứa mảng, chuỗi in mặc định của mảng không diễn đạt các giá trị bên trong một cách hữu ích cho việc dự đoán.

Không thay đích bằng kiểu Object hay kiểu thô chỉ để làm một lời gọi sai ý nghĩa biên dịch được. Một lời gọi thêm cả mảng hoặc cả List như một phần tử có thể hợp lệ về kiểu nhưng vẫn không đúng yêu cầu cần từng phần tử nhỏ hơn. Kiểu dữ liệu và số phần tử mong muốn phải nhất quán.

## 12. Thực hành với kết quả dự đoán được

### Bài 1: Thêm ba đối số vào List có dữ liệu

Bắt đầu từ `[base]`, thêm A, B, A bằng tiện ích. Dự đoán nội dung, kích thước và boolean trước khi chạy.

Kết quả cần có `[base, A, B, A]`, kích thước bốn và true. Gọi tiếp với không phần tử trên đích ArrayList hợp lệ để kiểm tra trường hợp không thay đổi.

### Bài 2: Cùng đối số nhưng đích là Set

Bắt đầu từ LinkedHashSet chứa A. Thêm A, B, A rồi lặp lại cùng nhóm đối số.

Lần đầu có giá trị mới B nên trả true, lần sau không có giá trị mới nên trả false. Kích thước cuối vẫn bằng hai. Hãy giải thích vì sao số đối số không là số phần tử mới được bảo đảm.

### Bài 3: Chọn từng chuỗi hay cả mảng

Có một `String[]` gồm ba tên. Cần hai kết quả khác nhau: một `List<String>` có ba phần tử và một `List<String[]>` có một phần tử.

Hãy ghi kiểu rõ cho cả hai đích, dự đoán size rồi kiểm chứng. Thay một ô của mảng sau khi thêm để quan sát sự khác nhau giữa đã lấy các tham chiếu String và đang giữ chính mảng.

### Bài 4: Từ mảng nguyên thủy đến List số

Có `int[]` gồm ba số. Một yêu cầu cần lưu từng mảng số như một lô; yêu cầu khác cần `List<Integer>` chứa từng số.

Hãy chọn `List<int[]>` cho yêu cầu đầu và một bước lấy từng giá trị cho yêu cầu sau. Tiêu chí đạt: giải thích được vì sao lời gọi với mảng nguyên thủy không tự cung cấp ba đối số Integer.

### Bài 5: Null ở đúng tầng dữ liệu

Dùng Array`List<String>` làm đích. Kiểm tra một phần tử String null và một mảng String null bằng hai kiểu ép rõ ràng.

Trước khi chạy, dự đoán ca nào có một phần tử, ca nào không có mảng hợp lệ để duyệt. Sau đó đổi đích sang một cấu trúc từ chối null để nhận biết chính sách đích cũng là một phần của kết quả.

### Bài 6: Không giả định cập nhật toàn bộ

Dùng ArrayDeque và một nhóm có phần tử hợp lệ, null rồi một phần tử hợp lệ khác. Quan sát dữ liệu sau lỗi, rồi mô tả một quy trình tiếp nhận cần kiểm tra đầu vào trước khi công bố.

Tiêu chí đạt là nhận ra lời gọi tiện ích không hứa hoàn tác. Không dùng kết quả cập nhật một phần cụ thể như một quy tắc nghiệp vụ cần được giữ ở mọi đích hoặc mọi phiên bản.

### Tự kiểm tra

- **Collections.addAll có tạo đích không?** Không. Collection đích phải được cung cấp.
- **Giá trị trả về có là số phần tử thêm được không?** Không. Nó cho biết có thay đổi hay không khi lời gọi hoàn tất bình thường.
- **Varargs có tự trải mọi collection lồng không?** Không. Phải đọc kiểu phần tử và tham số mảng của lời gọi.
- **Một `int[]` có tự thành nhiều Integer không?** Không. Lấy từng giá trị nếu mục tiêu là `List<Integer>`.
- **Thêm một null và truyền mảng null có giống nhau không?** Không. Một bên là phần tử của dãy, bên kia là chính đối tượng mảng không tồn tại.
- **Điều gì quyết định thứ tự và phần tử trùng?** Hợp đồng của collection đích, không chỉ thứ tự viết các đối số.
- **Đã thêm tham chiếu thì phần tử có độc lập trạng thái với nguồn không?** Không mặc nhiên. Cần chính sách sao chép hoặc kiểu giá trị phù hợp nếu yêu cầu độc lập trạng thái.

