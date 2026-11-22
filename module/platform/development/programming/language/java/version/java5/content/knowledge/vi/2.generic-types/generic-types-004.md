# Kiểu tham số hóa và đối số kiểu cụ thể

## 1. Từ một khuôn generic đến một kiểu có thể sử dụng

Giả sử cần một hộp chỉ chứa chuỗi tên sản phẩm. Nếu hộp khai báo giá trị là `Object`, mã sử dụng không biết chắc lấy ra một chuỗi hay một đối tượng khác. Với generic, người viết hộp mô tả quan hệ kiểu một lần; người sử dụng chọn kiểu dữ liệu phù hợp cho từng nơi dùng.

Trong khai báo `class Box<T>`, `T` là **tham số kiểu** (type parameter): tên đại diện cho một kiểu chưa được chọn. Khi sử dụng `Box<String>`, `String` là **đối số kiểu** (type argument) được cung cấp cho `T`; toàn bộ `Box<String>` là một **kiểu tham số hóa** (parameterized type).

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Khai báo kiểu generic | `class Box<T>` | Định nghĩa hộp theo một tham số kiểu `T` |
| Tham số kiểu | `T` | Tên dùng trong khai báo hộp và các thành viên phụ thuộc kiểu |
| Đối số kiểu cụ thể | `String` | Kiểu được chọn cho một lần tham số hóa |
| Kiểu tham số hóa | `Box<String>` | Kiểu hộp với quan hệ kiểu đã xác định |
| Biến | `nameBox` | Tên của biến có thể tham chiếu tới hộp tương thích |
| Đối tượng | `new Box<>("Java")` | Đối tượng được tạo khi chương trình thực thi |

Đừng đọc `Box<String>` như “một chuỗi”. Nó là kiểu của **hộp chứa giá trị được kiểm tra theo kiểu `String`**. Cũng đừng nhầm kiểu với tên biến hoặc với đối tượng: nhiều biến cùng kiểu có thể tham chiếu tới những hộp khác nhau, và hai biến cũng có thể cùng tham chiếu tới một hộp.

Generic là đặc điểm được đưa vào Java từ Java 5 và vẫn dùng trong mã Java hiện hành. Bài này dùng JDK 17 trở lên để chạy, cùng cú pháp `<>` hiện hành; không yêu cầu viết mã theo giới hạn cú pháp của JDK 5.

## 2. Đối số kiểu làm thay đổi hợp đồng sử dụng như thế nào?

Xét phần khai báo sau. Đây là đoạn minh họa; chương trình đầy đủ nằm ở mục 5.

```java
static final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Khi trình biên dịch kiểm tra mã sử dụng một biểu thức có kiểu `Box<String>`, các vị trí dùng `T` trong hợp đồng của các thành viên trên được xem theo đối số kiểu `String`: hàm khởi tạo nhận `String`, `get()` trả về `String`, còn `set(...)` nhận `String`.

```java
Box<String> nameBox = new Box<>("Java");
nameBox.set("Generics");
String name = nameBox.get();
int length = nameBox.get().length();
```

Nhờ kiểu trả về là `String`, có thể gọi `length()` mà không ép kiểu. Nếu thêm dòng `nameBox.set(42);`, trình biên dịch từ chối: giá trị số nguyên không tương thích với đối số `String` của `set` tại nơi sử dụng này.

Nếu thay bằng `Box<Integer>`, `get()` được kiểm tra là trả về `Integer` và `set(...)` nhận `Integer`. Hai lần tham số hóa cùng dùng một khai báo `Box<T>`; chúng không buộc người viết phải sao chép lớp thành `StringBox`, `IntegerBox` rồi duy trì nhiều bản logic giống nhau.

Cách nhìn “thay `T` bằng đối số kiểu” giúp hiểu **kiểm tra kiểu lúc biên dịch**. Nó không có nghĩa JVM tạo riêng một bản lớp `Box` cho từng đối số kiểu.

Quy tắc này cũng áp dụng cho thư viện chuẩn: với `List<String>`, phương thức `get(int)` trả về `String` theo kiểu tĩnh, còn `add(...)` kiểm tra phần tử mới là `String` tương thích. Tuy nhiên, khả năng thêm phần tử còn phụ thuộc đối tượng thực thi danh sách: một danh sách không cho sửa vẫn có thể từ chối thao tác `add` lúc chạy.

Đối chiếu quy tắc về kiểu tham số hóa và kiểu của thành viên tại [JLS §4.5 và §4.5.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5).

## 3. Chọn đối số kiểu cụ thể

### 3.1. Dùng kiểu tham chiếu, kể cả kiểu do mình định nghĩa

`String`, `Integer`, một lớp `Product`, một interface như `Runnable` hoặc một kiểu mảng như `String[]` đều có thể là đối số kiểu nếu thỏa mãn ràng buộc của khai báo generic. Không có quy tắc bắt buộc đối số kiểu phải là lớp `final`, và không cần tạo đối tượng của đối số kiểu ngay lúc khai báo.

```java
Box<Integer> countBox = new Box<>(3);
Box<String[]> tagsBox = new Box<>(new String[] {"java", "types"});
```

`int` là kiểu nguyên thủy nên `Box<int>` không hợp lệ. Dùng `Box<Integer>`; Java có thể tự đóng hộp giá trị `3` thành `Integer`. Khi lấy ra rồi mở hộp sang `int`, cần nhớ một giá trị `Integer` bằng `null` sẽ gây `NullPointerException`. Generic không tự biến giá trị tham chiếu thành giá trị luôn khác `null`.

### 3.2. Số lượng, thứ tự và ràng buộc phải khớp khai báo

Với interface `Map<K, V>`, đối số thứ nhất là kiểu khóa, đối số thứ hai là kiểu giá trị:

```java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("book", 3);
Integer quantity = stock.get("book");
```

`Map<String, Integer>` và `Map<Integer, String>` có vai trò khóa/giá trị khác nhau. Không được bỏ thiếu một đối số hoặc cung cấp thừa đối số. Muốn xác định ý nghĩa từng vị trí, đọc khai báo và tài liệu của kiểu generic thay vì suy đoán từ các tên chữ cái.

Nếu khai báo có giới hạn như `class NumericBox<T extends Number>`, đối số kiểu phải nằm trong phạm vi giới hạn đó: `NumericBox<Integer>` hợp lệ, còn `NumericBox<String>` không hợp lệ. Bài này chỉ cần nhận biết giới hạn khi chọn kiểu; việc thiết kế giới hạn là chủ đề riêng.

### 3.3. Kiểu lồng nhau vẫn là một đối số kiểu

```java
Map<String, List<Integer>> scoresByStudent = new LinkedHashMap<>();
scoresByStudent.put("An", List.of(8, 9));
List<Integer> scores = scoresByStudent.get("An");
```

Đọc từ ngoài vào: một `Map` có khóa `String`, mỗi giá trị là `List<Integer>`; mỗi phần tử trong danh sách được kiểm tra theo `Integer`. `List<Integer>` là **một** đối số kiểu của `Map`, dù bản thân nó cũng là kiểu tham số hóa. Chỉ số lượng đối số ở cấp hiện tại mới được đối chiếu với tham số của cấp đó.

Với khóa không tồn tại, `Map.get` có thể trả về `null`; chọn đối số kiểu đúng không loại bỏ yêu cầu xử lý tình huống không tìm thấy dữ liệu. Hợp đồng của API vẫn cần được đọc độc lập với hợp đồng generic.

## 4. Kiểu bên trái, kiểu bên phải và dấu `<>`

Trong dòng:

```java
List<String> names = new ArrayList<>();
```

`List<String>` là kiểu khai báo của biến. `ArrayList<>` là lớp được dùng để tạo đối tượng; dấu `<>` yêu cầu trình biên dịch suy luận đối số kiểu trong ngữ cảnh này là `String`. Điều đó hợp lệ vì `ArrayList<String>` triển khai `List<String>`.

Kiểu của biến quyết định thành viên nào có thể được gọi trong mã nguồn. Việc đối tượng thực tế là `ArrayList` không khiến biến `names` tự có mọi phương thức chỉ riêng `ArrayList` mới có. Chọn interface cho biến là cách để nơi sử dụng phụ thuộc vào hợp đồng cần thiết.

`<>` không có nghĩa “không có kiểu”, “mọi kiểu” hay “kiểu sẽ tự đổi lúc chạy”. Một khi kiểu đã được kiểm tra, không thể dùng cùng biến này để thêm một phần tử `Integer` chỉ vì danh sách đang rỗng.

Với `var`, phải chú ý ngữ cảnh suy luận:

```java
List<String> explicit = new ArrayList<>();
var inferred = new ArrayList<String>();
var broad = new ArrayList<>();
```

Ba biến lần lượt có kiểu tĩnh `List<String>`, `ArrayList<String>` và `ArrayList<Object>`. Trong dòng cuối, không có kiểu đích `List<String>` để định hướng suy luận, và hàm khởi tạo không nhận phần tử để cung cấp thêm thông tin. Vì vậy không được mặc định rằng `var` sẽ chọn `String` theo ý định của người viết.

Trong bài học về generic, khai báo rõ `List<String>` thường giúp người đọc nhìn thấy hợp đồng ngay tại biến. `var` vẫn là lựa chọn hợp lệ khi kiểu đã rõ từ vế phải.

## 5. Chương trình chạy đầy đủ

Lưu đoạn sau vào tệp `ParameterizedTypesDemo.java`. Chương trình dùng hộp tự định nghĩa, danh sách và bảng tồn kho; mỗi nơi chọn đối số kiểu tương ứng với dữ liệu của mình.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ParameterizedTypesDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box<String> label = new Box<>("Java");
        label.set("Generics");
        String text = label.get();
        System.out.println(text + ": " + text.length());

        Box<Integer> quantity = new Box<>(3);
        quantity.set(quantity.get() + 2);
        System.out.println("quantity=" + quantity.get());

        List<String> topics = new ArrayList<>();
        topics.add("types");
        topics.add("collections");
        System.out.println(topics);

        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        scores.put("An", List.of(8, 9));
        System.out.println("An=" + scores.get("An"));

        Box<Number> measurement = new Box<>(10);
        measurement.set(2.5);
        System.out.println("measurement=" + measurement.get());

        var broad = new ArrayList<>();
        broad.add("book");
        broad.add(2);
        System.out.println("broad=" + broad);

        Box<String> first = new Box<>("one");
        Box<Integer> second = new Box<>(2);
        System.out.println("same runtime class="
                + (first.getClass() == second.getClass()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all ParameterizedTypesDemo.java
java ParameterizedTypesDemo
```

Stdout:

```text
Generics: 8
quantity=5
[types, collections]
An=[8, 9]
measurement=2.5
broad=[book, 2]
same runtime class=true
```

Ở phép cộng `quantity.get() + 2`, giá trị `Integer` được mở hộp để tính toán, kết quả được đóng hộp khi truyền vào `set`. Hộp `measurement` có đối số `Number`, nên có thể nhận một `Integer` rồi một `Double`; nó không bị khóa thành `Integer` chỉ vì giá trị khởi tạo là `10`.

Danh sách `broad` nhận cả chuỗi và số vì kiểu phần tử suy luận là `Object`. Đây là một hợp đồng khác với `List<String>`, không phải generic bị vô hiệu hóa.

Dòng cuối cho thấy hai hộp với đối số kiểu khác nhau vẫn có cùng lớp lúc chạy trong ví dụ này. Cơ chế xóa kiểu (type erasure) không tạo một lớp JVM riêng cho mỗi đối số cụ thể. Tuy vậy, các biến `first` và `second` vẫn có kiểu tĩnh khác nhau; việc cùng lớp lúc chạy không cho phép gán chúng cho nhau hoặc tùy tiện ép kiểu.

Đối chiếu cơ chế xóa kiểu tại [JLS §4.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6), và quy tắc suy luận khi tạo đối tượng tại [JLS §15.9](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9).

## 6. Các lỗi dễ gặp khi suy luận từ đối số kiểu

### 6.1. Tưởng quan hệ kế thừa của phần tử tự lan sang hộp

`Integer` là kiểu con của `Number`, nhưng `Box<Integer>` không là kiểu con của `Box<Number>`. Tương tự, `List<String>` không là kiểu con của `List<Object>`.

Đoạn sau cố ý không biên dịch; có thể đặt các dòng này trong `main` của chương trình trên để thử lỗi:

```java
Box<Integer> integers = new Box<>(1);
Box<Number> numbers = integers; // Lỗi biên dịch
```

Nếu phép gán được cho phép, gọi `numbers.set(2.5)` sẽ đưa một `Double` vào chính hộp mà `integers.get()` hứa trả về `Integer`. Việc từ chối phép gán bảo vệ hợp đồng của hộp ban đầu. Đây là tính bất biến (invariance) của các lần tham số hóa như trên.

Có thể khai báo một hộp `Box<Number>` ngay từ đầu khi cần chứa nhiều kiểu con của `Number`, như chương trình minh họa. Nếu mục tiêu là nhận nhiều lần tham số hóa trong một API, cần học tiếp wildcard và giới hạn thích hợp; không giải quyết bằng ép kiểu cưỡng ép.

### 6.2. Nhầm `Object` với kiểu chưa biết

`List<Object>` là danh sách có đối số kiểu **đã xác định là `Object`**. Nó cho phép thêm các giá trị tham chiếu thuộc nhiều lớp khác nhau, nhưng không nhận phép gán trực tiếp từ `List<String>`.

`List<?>` cũng là kiểu tham số hóa, nhưng đối số của nó là wildcard, không phải đối số kiểu cụ thể `Object`. Nó biểu đạt rằng kiểu phần tử cụ thể chưa được biết tại nơi sử dụng; vì vậy không được tự ý thêm một chuỗi hay số vào đó. Bài này chỉ phân biệt ý nghĩa, chưa triển khai quy tắc đọc/ghi của wildcard.

### 6.3. Nhầm tham số kiểu với một lớp có tên cố định

Trong `class Holder<T>`, `T` được khai báo bởi chính lớp generic. Trong mã sử dụng `Holder<String>`, `String` là kiểu đã tồn tại. Tên `T`, `E`, `K`, `V` là quy ước đặt tên, không phải các từ khóa đặc biệt của Java.

Cũng không nên nghĩ mọi đối số kiểu đều phải cụ thể: trong khai báo `class Wrapper<U>` có thể dùng `Box<U>`. Khi ấy `U` vẫn là biến kiểu của phạm vi bên ngoài. Trường hợp `Box<String>` là trường hợp chọn một đối số cụ thể, không phải định nghĩa bao quát mọi cách tham số hóa.

### 6.4. Cho rằng đúng kiểu đồng nghĩa đúng dữ liệu

`Box<String>` không khẳng định chuỗi có nội dung, khác `null` hoặc hợp lệ theo nghiệp vụ. `List<Integer>` cũng không khẳng định mọi số đều dương. Các điều kiện ấy cần kiểm tra giá trị, thiết kế hàm khởi tạo hoặc quy tắc API riêng. Generic bảo vệ quan hệ kiểu; nó không thay thế kiểm tra dữ liệu.

Trong mã mới, hãy giữ đầy đủ thông tin đối số kiểu và xử lý cảnh báo biên dịch thay vì che chúng bằng `@SuppressWarnings`. Không bỏ danh sách đối số kiểu của một kiểu generic chỉ để làm phép gán đang lỗi trở nên có thể viết được.

## 7. Tự kiểm tra

1. Trong `Map<String, List<Integer>>`, đâu là kiểu tham số hóa bên ngoài và hai đối số kiểu ở cấp đó?
2. Vì sao `Box<Number> x = new Box<>(1);` hợp lệ nhưng gán một biến `Box<Integer>` đã có sang `Box<Number>` lại lỗi?
3. Với khai báo `Box<String> b`, kiểu tĩnh của `b.get()` là gì? `b.set(10)` bị từ chối vào giai đoạn nào?
4. Nếu viết `var items = new ArrayList<>();`, vì sao không nên kỳ vọng `items` có kiểu `List<String>`?
5. Một `Box<String>` có bảo đảm giá trị trả về luôn khác `null` không?

Đáp án:

1. Kiểu bên ngoài là `Map<String, List<Integer>>`; hai đối số là `String` và `List<Integer>`. Bên trong đối số thứ hai, `Integer` là đối số của `List`.
2. Ở phép tạo đầu tiên, ngữ cảnh đích định hướng tạo `Box<Number>` và giá trị `1` tương thích với `Number` sau đóng hộp. Phép gán thứ hai đòi coi một hộp chỉ chấp nhận `Integer` như hộp có thể chấp nhận mọi `Number`, nên bị từ chối.
3. `b.get()` có kiểu tĩnh `String`; `b.set(10)` bị từ chối khi biên dịch.
4. Vế phải không cung cấp ngữ cảnh chọn `String`; trường hợp này suy luận `ArrayList<Object>`. `var` lưu kiểu suy luận từ biểu thức khởi tạo, không tự chọn theo cách ta định dùng biến sau đó.
5. Không. Với lớp `Box` trong bài, `new Box<String>(null)` hợp lệ; quy tắc không nhận `null` phải được thiết kế thêm nếu cần.

Khi gặp một kiểu như `Map<String, List<Integer>>` trong API thực tế, hãy đọc từ ngoài vào, đối chiếu từng đối số với tham số trong khai báo, rồi xác định kiểu đầu vào và đầu ra của thao tác định dùng. Đây là cách biến cú pháp generic thành một hợp đồng sử dụng cụ thể.
