# Boxing trong phép gán, truyền đối số và collection

## 1. Khi một giá trị nguyên thủy cần đi vào API dùng đối tượng

`int`, `long`, `boolean` và các kiểu nguyên thủy khác biểu diễn giá trị mà không phải là đối tượng wrapper. Trong khi đó, nhiều API cần tham chiếu đối tượng, chẳng hạn `Integer` hoặc phần tử của `List<Integer>`.

**Boxing** là phép chuyển một giá trị nguyên thủy sang biểu diễn wrapper tương ứng. Khi Java tự thực hiện phép chuyển trong ngữ cảnh được phép, ta thường gọi đó là **autoboxing**.

```java
int amount = 5;
Integer boxedAmount = amount;
```

Biến `amount` vẫn là `int`. Phép gán khởi tạo biến `boxedAmount` cần một tham chiếu `Integer`, nên giá trị số nguyên được boxing. Việc này không làm đổi kiểu của biến nguồn.

Có thể hình dung trường hợp `int` sang `Integer` tương tự việc dùng `Integer.valueOf(amount)`. Tuy nhiên, không nên suy ra boxing luôn tạo một đối tượng mới riêng biệt cho mỗi lần xuất hiện; các wrapper/API có thể tái sử dụng đối tượng theo những bảo đảm và cơ chế của chúng.

Boxing vẫn là cơ chế dùng trong mã Java hiện hành. Các ví dụ trong bài chạy bằng JDK 17 trở lên.

## 2. Cặp kiểu nguyên thủy và wrapper

| Kiểu nguyên thủy | Wrapper tương ứng | Ví dụ boxing |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean active = true;` |
| `byte` | `Byte` | `byte b = 1; Byte value = b;` |
| `short` | `Short` | `short s = 2; Short value = s;` |
| `char` | `Character` | `Character letter = 'A';` |
| `int` | `Integer` | `Integer count = 3;` |
| `long` | `Long` | `Long id = 3L;` |
| `float` | `Float` | `Float ratio = 1.5f;` |
| `double` | `Double` | `Double measure = 1.5;` |

Các ví dụ trong bảng là câu lệnh đặt trong một phạm vi phù hợp. Mỗi kiểu nguyên thủy có wrapper tương ứng; boxing không tùy ý chọn một wrapper số khác chỉ vì cả hai cùng biểu diễn được giá trị.

Ví dụ `3` là literal `int`, còn `3L` là literal `long`. Sự khác nhau đó quan trọng khi đích là `Integer` hoặc `Long`.

Quy tắc chuyển đổi được mô tả tại [JLS §5.1.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7).

## 3. Boxing trong phép gán

### 3.1. Gán trực tiếp sang wrapper tương ứng

```java
int primitive = 5;
Integer boxed = primitive;
Long longBox = 5L;
```

`boxed` giữ một tham chiếu tới wrapper biểu diễn giá trị 5. Wrapper như `Integer` là bất biến: khi một biến `Integer` được gán một giá trị khác, biến đổi tham chiếu của nó không sửa trường giá trị của đối tượng wrapper cũ.

Đừng nhầm boxing với mở rộng số nguyên thủy:

```java
long widePrimitive = 5; // int -> long: mở rộng nguyên thủy, không boxing
```

### 3.2. Boxing rồi mở rộng kiểu tham chiếu

```java
Number number = 5;
Object object = 5;
```

Giá trị `int` có thể được boxing thành `Integer`, rồi tham chiếu được dùng theo kiểu cha phù hợp như `Number` hoặc `Object`. Đối tượng không vì thế biến thành một đối tượng `Number` khác; kiểu runtime vẫn có thể là `Integer`.

`Number` và `Object` không phải các wrapper riêng cho `int`. Chúng là những kiểu tham chiếu có thể nhận wrapper tương thích.

### 3.3. Không tự nối mọi phép chuyển số rồi boxing

```java
// Long invalid = 5; // Lỗi biên dịch nếu bỏ chú thích
Long validLiteral = 5L;
int source = 5;
Long validConversion = (long) source;
```

Java không tự áp dụng chuỗi “mở rộng `int` thành `long`, rồi boxing thành `Long`” trong phép gán `Long invalid = 5`. Cần làm cho biểu thức nguồn có kiểu `long` phù hợp, chẳng hạn dùng hậu tố `L` hoặc phép chuyển rõ ràng.

Riêng ngữ cảnh phép gán có một số quy tắc cho hằng số nguyên nằm trong phạm vi biểu diễn. Ví dụ `Byte small = 1;` hợp lệ nhờ chuyển hằng số phù hợp sang `byte` rồi boxing. Không được lấy trường hợp hằng số này làm quy tắc rằng mọi biến `int` đều gán trực tiếp cho `Byte`.

Tham khảo các phép chuyển được cho phép trong [JLS §5.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2).

## 4. Boxing khi truyền đối số

Nếu phương thức nhận `Integer`:

```java
static void showInteger(Integer value) {
    System.out.println("integer argument=" + value);
}
```

Thì lời gọi `showInteger(12)` có thể boxing giá trị `int` thành `Integer` để đáp ứng tham số. Một phương thức nhận `Number` hoặc `Object` cũng có thể nhận giá trị nguyên thủy qua boxing kết hợp với mở rộng tham chiếu phù hợp.

Tuy nhiên, ngữ cảnh gọi phương thức không có mọi quy tắc của phép gán hằng số:

```java
Byte small = 1;       // Hợp lệ trong ngữ cảnh phép gán
// showByte(1);       // Lỗi nếu showByte nhận Byte
showByte((byte) 1);   // byte -> Byte: hợp lệ
```

Trong ví dụ này, `showByte` là phương thức nhận `Byte`, được định nghĩa trong chương trình đầy đủ. Literal `1` có kiểu `int`; lời gọi phương thức không tự thu hẹp hằng số theo cùng cách phép gán `Byte small = 1` đã làm.

Tương tự, nếu phương thức nhận `Long`, truyền `1L` hoặc một biểu thức `long` phù hợp; không kỳ vọng đối số `int` được tự mở rộng rồi boxing thành `Long`.

### Nạp chồng phương thức có thể chọn trước khi cần boxing

Nếu có hai phương thức `choose(long)` và `choose(Integer)`, lời gọi `choose(12)` chọn bản nhận `long`. Mở rộng nguyên thủy đã đủ làm phương thức đầu phù hợp trong giai đoạn chọn trước khi xét các lời gọi cần boxing.

Không nên nghĩ boxing luôn được ưu tiên chỉ vì wrapper có tên gần với kiểu nguyên thủy. Khi API có overload, cần kiểm tra chữ ký thực tế và các quy tắc chọn phương thức.

Đối chiếu ngữ cảnh lời gọi tại [JLS §5.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3).

## 5. Boxing khi làm việc với collection

### 5.1. Collection generic dùng kiểu tham chiếu

`List<int>` không hợp lệ. Với collection chuẩn chứa các giá trị số nguyên, thường dùng `List<Integer>`:

```java
List<Integer> values = new ArrayList<>();
values.add(10);
values.add(Integer.valueOf(20));
```

Các import cần thiết là `java.util.List` và `java.util.ArrayList`. Ở `add(10)`, giá trị `int` được boxing để phù hợp hợp đồng phần tử `Integer`. Ở lời gọi thứ hai, đối số đã là một `Integer`, nên không cần thêm một bước boxing từ `int` tại chỗ truyền đối số đó.

Danh sách lưu tham chiếu wrapper, không biến thành một mảng nguyên thủy `int[]`. Chọn `Integer` trong generic vẫn giữ việc kiểm tra kiểu: không thể thêm một chuỗi tùy ý vào danh sách.

### 5.2. Đọc wrapper khác với mở hộp

```java
Integer wrapper = values.get(0);
int primitive = values.get(0);
values.set(0, values.get(0) + 1);
```

`get(0)` được dùng theo kiểu trả về `Integer`. Dòng đầu lấy wrapper. Dòng thứ hai cần `int`, nên thực hiện **unboxing** — hướng chuyển ngược với boxing. Ở dòng thứ ba, giá trị được mở hộp để cộng; kết quả `int` lại được boxing khi truyền vào `set`.

Nếu wrapper bằng `null`, một thao tác mở hộp có thể gây `NullPointerException`. Autoboxing không bảo đảm rằng mọi giá trị đọc từ collection luôn khác `null`.

### 5.3. Map cũng áp dụng ở khóa hoặc giá trị phù hợp

```java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("book", 3);
Integer quantity = stock.get("book");
```

Giá trị `3` được boxing khi truyền cho tham số giá trị `Integer`. Khi lấy ra, `quantity` là wrapper; nếu gán vào `int`, sẽ có thêm bước mở hộp.

Với một khóa không tồn tại, `Map.get` có thể trả `null`. Việc `put` dùng autoboxing ở một nơi không loại bỏ yêu cầu xử lý trường hợp không có dữ liệu ở nơi đọc.

### 5.4. List<Long> không tự nhận literal int

```java
List<Long> ids = new ArrayList<>();
ids.add(1L);
// ids.add(1); // Lỗi biên dịch nếu bỏ chú thích
```

Giá trị `1` có kiểu `int`; nó không tự trở thành `Long` chỉ vì danh sách đang rỗng hoặc đích mong muốn là `Long`. Dùng biểu thức `long` khi đó đúng là kiểu dữ liệu của API.

## 6. Chương trình chạy đầy đủ

Lưu thành `BoxingContextsDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class BoxingContextsDemo {
    static void showInteger(Integer value) {
        System.out.println("integer argument=" + value);
    }

    static void showByte(Byte value) {
        System.out.println("byte argument=" + value);
    }

    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        int primitive = 5;
        Integer boxed = primitive;
        Number number = primitive;
        Object object = primitive;
        Long longBox = 5L;
        Byte small = 1;

        System.out.println("boxed=" + boxed);
        System.out.println("number class=" + number.getClass().getSimpleName());
        System.out.println("object class=" + object.getClass().getSimpleName());
        System.out.println("long box=" + longBox);
        System.out.println("small=" + small);

        showInteger(12);
        showByte((byte) 1);
        System.out.println("overload=" + choose(12));

        List<Integer> values = new ArrayList<>();
        values.add(10);
        values.add(Integer.valueOf(20));
        int first = values.get(0);
        values.set(0, values.get(0) + 1);
        System.out.println("first=" + first);
        System.out.println("values=" + values);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("book", 3);
        Integer quantity = stock.get("book");
        System.out.println("quantity=" + quantity);

        List<Long> ids = new ArrayList<>();
        ids.add(1L);
        System.out.println("ids=" + ids);

        List<Integer> removal = new ArrayList<>(List.of(10, 20, 10));
        removal.remove(1);
        System.out.println("after index removal=" + removal);
        removal.remove(Integer.valueOf(10));
        System.out.println("after value removal=" + removal);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror BoxingContextsDemo.java
java BoxingContextsDemo
```

Stdout:

```text
boxed=5
number class=Integer
object class=Integer
long box=5
small=1
integer argument=12
byte argument=1
overload=long
first=10
values=[11, 20]
quantity=3
ids=[1]
after index removal=[10, 10]
after value removal=[10]
```

Hai dòng lớp runtime cho thấy mở rộng tham chiếu sang `Number` hoặc `Object` không làm đổi wrapper của giá trị `int`. Dòng overload cho thấy không phải lời gọi có giá trị `int` nào cũng chọn wrapper nếu đã có lựa chọn nguyên thủy phù hợp trước đó.

Các dòng cuối minh họa một bẫy API cần đọc đúng: `remove(1)` chọn overload xóa theo chỉ số; `remove(Integer.valueOf(10))` chọn thao tác xóa theo giá trị đối tượng. Boxing không làm một đối số `int` mặc định được hiểu là “giá trị phần tử cần xóa”.

## 7. Những điều autoboxing không làm thay

### Không chuyển nội dung chuỗi thành số

`"12"` là `String`, không phải một `int` chờ được boxing. Muốn chuyển nội dung thành số, dùng API phân tích phù hợp như `Integer.parseInt` hoặc `Integer.valueOf(String)` và xử lý định dạng không hợp lệ. Đó là chuyển đổi dữ liệu, không phải autoboxing.

### Không đổi toàn bộ một collection sang kiểu phần tử khác

`List<Integer>` không tự trở thành `List<Long>` hay `List<Number>` bằng một phép boxing. Mỗi danh sách có hợp đồng generic của nó; muốn đổi kiểu phần tử cần một thao tác chuyển đổi phù hợp hoặc một hợp đồng nhận dữ liệu khác.

### Không làm wrapper thành đối tượng sửa được

`Integer` giữ giá trị bất biến. Một biểu thức cập nhật biến wrapper có thể mở hộp, tính toán rồi boxing lại; nó không sửa mọi nơi đang tham chiếu tới wrapper cũ. Với collection, muốn lưu kết quả mới phải cập nhật phần tử bằng API phù hợp.

### Không bảo đảm mỗi lần boxing có một danh tính mới

Không dùng `==` giữa hai wrapper để kết luận chúng biểu diễn cùng giá trị. Khi cần so sánh giá trị wrapper, dùng hợp đồng so sánh phù hợp như `equals` hoặc `Objects.equals` khi có thể có `null`.

Việc tái sử dụng wrapper cũng có nghĩa không nên tính toán chi phí bằng giả định “mỗi dấu boxing chắc chắn cấp phát một đối tượng mới”. Nhưng boxing vẫn có thể tạo công việc và dùng bộ nhớ; trong những luồng tính toán số lượng lớn, cân nhắc kiểu nguyên thủy khi hợp đồng API cho phép và đo hiệu năng nếu cần.

Xem hợp đồng tạo wrapper và lưu ý về giá trị tại [Integer.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

## 8. Tự kiểm tra

1. `Integer x = 5` có làm biến hoặc literal nguồn đổi thành kiểu đối tượng không?
2. `Object x = 5` thường nhận wrapper tương ứng của kiểu nguyên thủy nào?
3. Vì sao `Long x = 5` không giống `long x = 5` về tính hợp lệ?
4. `List<Integer>.get` trả wrapper hay giá trị `int` nguyên thủy theo kiểu khai báo?
5. Vì sao `showByte(1)` có thể lỗi dù `Byte b = 1` hợp lệ?

Đáp án:

1. Không. Boxing phục vụ ngữ cảnh đích; kiểu nguồn vẫn được xác định theo khai báo/biểu thức.
2. Literal `5` là `int`, nên wrapper tương ứng là `Integer`, rồi tham chiếu được dùng như `Object`.
3. Dòng nhận `long` chỉ cần mở rộng nguyên thủy; dòng nhận `Long` không cho tự ghép mở rộng `int` thành `long` rồi boxing theo cách đó.
4. `Integer`; khi nơi nhận yêu cầu `int` thì có thêm unboxing.
5. Phép gán có quy tắc đặc biệt cho một số hằng số nguyên phù hợp; ngữ cảnh gọi phương thức không tự dùng cùng quy tắc thu hẹp đó.

Khi gặp autoboxing, hãy xác định kiểu thật của biểu thức nguồn, kiểu đích mà API yêu cầu và ngữ cảnh chuyển đổi. Ba yếu tố đó quyết định Java được phép tự làm bước nào.
