# `equals()` của record: cùng lớp record và các thành phần tương ứng bằng nhau

## 1. Record và quan hệ bằng nhau theo giá trị

`record` là một dạng lớp trong Java để khai báo các **thành phần dữ liệu (record components)** làm trạng thái chính của đối tượng. Với Java 17:

```java
record Point(int x, int y) {}
```

Đây là một khai báo kiểu hợp lệ, chưa có `main` để chạy độc lập. Trình biên dịch tự sinh constructor chuẩn, accessor `x()`/`y()` và ba phương thức `equals(Object)`, `hashCode()`, `toString()` nếu lập trình viên không tự khai báo các phương thức tương ứng.

Với **`equals(Object)` do trình biên dịch sinh**, quy tắc là:

> Hai record bằng nhau khi chúng thuộc **cùng chính xác một lớp record** và **mọi cặp thành phần tương ứng đều bằng nhau**, theo ngữ nghĩa so sánh của kiểu thành phần.

Ví dụ `new Point(2, 3).equals(new Point(2, 3))` trả `true` mặc dù có hai đối tượng mới được tạo. `new Point(2, 3).equals(new Point(2, 4))` trả `false` vì thành phần `y` khác.

Điều này khác `==` trên hai tham chiếu: `==` hỏi chúng có trỏ tới **cùng một đối tượng** hay không. Một record phù hợp làm kiểu mang giá trị, ví dụ tọa độ, ngày giờ ghép từ các trường, đầu ra tính toán và khóa dữ liệu; nhưng phải thiết kế thành phần sao cho *tất cả các thành phần* thực sự thuộc ý nghĩa của giá trị logic.

Cần phân biệt **hành vi tự sinh** với trường hợp **tự override `equals`/`hashCode`**. Java cho phép viết hai phương thức này trong record. Khi làm vậy, lập trình viên chịu trách nhiệm hợp đồng bằng nhau và có thể chọn quy tắc khác mặc định (xem mục 8). Các phát biểu “cùng loại record và mọi component bằng nhau” trong bài áp dụng trực tiếp cho **phương thức tự sinh**.

## 2. Điều kiện đầu tiên: cùng chính xác record class

Hai record có tên thành phần, kiểu và dữ liệu giống nhau vẫn là hai loại khác nhau nếu chúng được khai báo thành hai lớp riêng:

```java
record Point(int x, int y) {}
record Coordinate(int x, int y) {}

Point p = new Point(2, 3);
Coordinate c = new Coordinate(2, 3);

System.out.println(p.equals(new Point(2, 3))); // true
System.out.println(p.equals(c));               // false
```

Đây là mảnh mã minh họa; chương trình hoàn chỉnh nằm ở mục 5. `Point` và `Coordinate` đều có hai `int` giống nhau nhưng là **hai record class khác nhau**. Equality tự sinh không làm phép so sánh cấu trúc xuyên lớp (structural equality). Hai record khác kiểu cũng không tự bằng nhau chỉ vì `toString()` trông gần giống hoặc `hashCode()` trùng nhau.

Một số hệ quả:

- Hai đối tượng `Point` khác tham chiếu nhưng cùng `x` và `y` có thể bằng nhau; `p1 == p2` không phải cách so giá trị.
- `Point` không mặc nhiên bằng `Coordinate` dù chúng có cùng dữ liệu và cùng tên thành phần.
- Một biến kiểu `Object` hoặc interface giữ instance `Point` vẫn sử dụng triển khai `Point.equals` tại runtime.
- `p.equals(null)` là `false`. Ngược lại, nếu **biến `p` chính nó là `null`**, `p.equals(...)` sẽ ném `NullPointerException`; có thể dùng `Objects.equals(p,q)` khi một trong hai tham chiếu có thể null.

Mọi record là lớp **ngầm định `final`** và trực tiếp mở rộng `java.lang.Record`. Vì vậy không có subclass nào của `Point` được phép thêm thành phần rồi override phép bằng nhau do `Point` cung cấp. Đây là khác biệt quan trọng so với một hệ phân cấp class thông thường, nơi lớp con dễ phá đối xứng của `equals` khi thêm điều kiện.

## 3. Điều kiện thứ hai: mọi component tương ứng phải bằng nhau

Sau khi xác định hai đối tượng thuộc cùng record class, `equals` tự sinh đánh giá mỗi **cặp component tương ứng theo thứ tự khai báo**. Ngữ nghĩa phụ thuộc vào kiểu của thành phần đó:

| Kiểu component | Quy tắc equality liên quan | Ví dụ |
| --- | --- | --- |
| `int`, `long`, `boolean`, `char` và các primitive không phải số thực | So giá trị nguyên thủy tương ứng | `Point(2,3)` bằng `Point(2,3)` |
| `float` và `double` | Ngữ nghĩa như `Float.compare`/`Double.compare` (hoặc phép bằng nhau của wrapper), có quy tắc riêng cho NaN và signed zero | `NaN` bằng `NaN`; `+0.0` khác `-0.0` |
| `String` | Dựa trên `String.equals`, so nội dung ký tự | Hai chuỗi khác tham chiếu cùng nội dung vẫn bằng |
| Kiểu tham chiếu khác | So bằng `Objects.equals`, gọi `equals` của giá trị khi khác null | Record lồng nhau, `List`, đối tượng khác |
| Mảng như `int[]` | `equals` kế thừa từ `Object`: so danh tính mảng | Hai mảng riêng cùng phần tử không tự bằng |
| `List` | Theo hợp đồng `List.equals` của đối tượng thành phần | Hai danh sách có cùng phần tử theo thứ tự có thể bằng |

**Không có cơ chế mặc định “tự so sâu mọi thứ”**. Record sử dụng cách mà **kiểu component** định nghĩa equality. Nếu chỉ một thành phần khác nhau, hai record không bằng nhau.

Ví dụ với component tham chiếu:

```java
record Label(String text) {}

boolean a = new Label(new String("core"))
        .equals(new Label(new String("core"))); // true
boolean b = new Label(null).equals(new Label(null)); // true
boolean c = new Label(null).equals(new Label("core")); // false
```

Đây là mảnh minh họa. Hai `String` có cùng nội dung nên `String.equals` trả đúng; hai component `null` cũng bằng nhau khi so qua `Objects.equals`. Không nên nói `record` dựa vào identity của mọi field: identity chỉ là quy tắc của **những kiểu component** không override equality.

### Tại sao `float` và `double` cần chú ý?

Primitive `double` có quy tắc toán tử `==` đặc biệt: `Double.NaN == Double.NaN` là `false`, còn `+0.0 == -0.0` là `true`. Nhưng `equals` tự sinh của record dùng ngữ nghĩa so sánh giúp duy trì tính phản xạ và tương thích hash:

- `new Measurement(Double.NaN).equals(new Measurement(Double.NaN))` là `true`.
- `new Measurement(+0.0).equals(new Measurement(-0.0))` là `false`.
- Các bit biểu diễn NaN khác nhau được quy về cùng lớp tương đương khi dùng ngữ nghĩa `Double.compare`/`Double.equals`.

Vì vậy **không thể giả định** record dùng phép `==` primitive đơn thuần cho mọi component. Nếu tự viết lại `equals` của record chứa số thực, cần đặc biệt kiểm tra NaN, số không có dấu và `hashCode`.

### Record component và ý nghĩa danh tính nghiệp vụ

`record Product(String sku, String displayName) {}` so cả `sku` **lẫn** `displayName`. Nếu chỉ `sku` xác định danh tính sản phẩm, một thay đổi của tên hiển thị sẽ khiến hai `Product` khác nhau theo equality mặc định. Khi thiết kế, cần quyết định record này biểu diễn **snapshot đầy đủ** hay **mã nhận dạng**, tránh dùng nhầm record snapshot làm khóa chỉ cần một ID.

## 4. Mảng và dữ liệu có thể thay đổi: giới hạn của record

### Component là mảng

```java
record NumberBox(int[] numbers) {}

NumberBox a = new NumberBox(new int[] {1, 2});
NumberBox b = new NumberBox(new int[] {1, 2});
System.out.println(a.equals(b)); // false
```

Hai mảng có nội dung bằng nhau nhưng là hai **đối tượng mảng** khác nhau. So `NumberBox` mặc định dùng equality của `int[]`, nghĩa là theo identity của mảng. Nếu muốn so nội dung mảng phải thiết kế điều đó tường minh, chẳng hạn dùng `Arrays.equals` trong cặp `equals`/`hashCode` được tự cài hoặc chuyển sang thành phần collection bất biến có ngữ nghĩa phù hợp.

Nếu hai record được tạo với **cùng tham chiếu mảng**, chúng có thể bằng nhau. Điều này chỉ xác nhận cùng đối tượng mảng, không chứng minh so từng phần tử.

### `final` không đồng nghĩa bất biến sâu

Record chứa các trường component `private final` nên không gán lại tham chiếu sau khi tạo. Nhưng phần tử tham chiếu vẫn có thể trỏ tới đối tượng mutable:

```java
record Permissions(java.util.List<String> roles) {}

java.util.List<String> mutable = new java.util.ArrayList<>();
mutable.add("READER");
Permissions p = new Permissions(mutable);

mutable.add("EDITOR"); // Nội dung List bên trong p đã thay đổi.
```

Đây là mảnh code minh họa. `List.equals` và `List.hashCode` dựa trên các phần tử, nên khi list thay đổi, `p.equals(...)` và `p.hashCode()` cũng có thể thay đổi. Điều đó nguy hiểm nếu `p` đã là khóa trong `HashMap` hay phần tử của `HashSet`.

Giải pháp với `List<String>` là sao chép và giữ một danh sách không thể sửa từ bên ngoài:

```java
record Permissions(java.util.List<String> roles) {
    Permissions {
        roles = java.util.List.copyOf(roles);
    }
}
```

Đây là record Java 17 hợp lệ, dùng compact constructor. `List.copyOf` tạo snapshot không thể sửa qua API thông thường và từ chối phần tử null; với `String` bất biến, việc giữ khóa ổn định đơn giản hơn. Với list các đối tượng mutable, list không sửa được **không tự bất biến hóa phần tử**.

Với mảng, chỉ clone ở constructor mà accessor vẫn công khai trả mảng nội bộ thì vẫn có nguy cơ bị sửa qua accessor. Cần cân nhắc sao chép phòng vệ ở cả đầu vào/đầu ra và định nghĩa equality/hash có mục đích.

## 5. Ví dụ Java 17+ biên dịch và chạy

Tạo tệp `RecordEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class RecordEqualityDemo {
    record Point(int x, int y) {}
    record Coordinate(int x, int y) {}
    record Label(String text) {}
    record NumberBox(int[] numbers) {}
    record Measurement(double value) {}

    public static void main(String[] args) {
        Point p1 = new Point(2, 3);
        Point p2 = new Point(2, 3);
        Point p3 = new Point(2, 4);
        Coordinate c = new Coordinate(2, 3);

        System.out.println("same reference: " + (p1 == p2));
        System.out.println("same record values: " + p1.equals(p2));
        System.out.println("different component: " + p1.equals(p3));
        System.out.println("different record class: " + p1.equals(c));
        System.out.println("equal hash: " + (p1.hashCode() == p2.hashCode()));

        Set<Point> points = new HashSet<>();
        points.add(p1);
        points.add(p2);
        System.out.println("set size: " + points.size());

        Map<Point, String> results = new HashMap<>();
        results.put(p1, "ready");
        System.out.println("map lookup: " + results.get(new Point(2, 3)));

        Label a = new Label(new String("core"));
        Label b = new Label(new String("core"));
        System.out.println("string component: " + a.equals(b));
        System.out.println("two null components: "
                + new Label(null).equals(new Label(null)));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        System.out.println("array contents: " + Arrays.equals(arrayA, arrayB));
        System.out.println("record with arrays: "
                + new NumberBox(arrayA).equals(new NumberBox(arrayB)));
        System.out.println("record shared array: "
                + new NumberBox(arrayA).equals(new NumberBox(arrayA)));

        System.out.println("NaN records equal: "
                + new Measurement(Double.NaN)
                        .equals(new Measurement(Double.NaN)));
        System.out.println("signed zero records equal: "
                + new Measurement(+0.0)
                        .equals(new Measurement(-0.0)));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 RecordEqualityDemo.java
java RecordEqualityDemo
```

Stdout chính xác:

```text
same reference: false
same record values: true
different component: false
different record class: false
equal hash: true
set size: 1
map lookup: ready
string component: true
two null components: true
array contents: true
record with arrays: false
record shared array: true
NaN records equal: true
signed zero records equal: false
```

Giải thích theo kết quả:

1. `p1` và `p2` là hai object khác nhau nên `== false`, nhưng cùng record class với cùng `x`/`y` nên `equals true`.
2. `p3` khác `y`; `Coordinate` khác kiểu runtime. Cả hai trường hợp không bằng `p1`.
3. Hai `Point` bằng nhau có cùng hash. `HashSet` chỉ giữ một giá trị logic; `HashMap` tìm được mục đã chèn bằng đối tượng `Point` mới cùng dữ liệu.
4. `String` component so theo nội dung; hai component cùng `null` cũng bằng. Hai mảng có phần tử giống nhau theo `Arrays.equals` nhưng hai `NumberBox` chứa mảng khác tham chiếu không bằng; nếu dùng cùng mảng thì bằng.
5. Record số thực xem NaN bằng NaN, nhưng phân biệt `+0.0` và `-0.0` theo ngữ nghĩa wrapper, khác trực giác từ phép `==` primitive.

## 6. `hashCode()` và hành vi collection

Ngoài `equals`, Java sinh `hashCode()` tương ứng với các thành phần. Bất biến bắt buộc là:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

Đây là biểu thức về hợp đồng. Chiều ngược lại **không đúng**: nhiều giá trị khác nhau có thể có cùng hash (va chạm). Giá trị số cụ thể của hash code record không phải thứ cần dựa vào khi thiết kế hợp đồng ứng dụng, vì cách kết hợp các thành phần không được hứa là một công thức công khai cố định cho mọi triển khai JDK.

Record có component ổn định làm khóa rất thuận tiện:

```java
record Key(String code, int version) {}

java.util.Map<Key, String> map = new java.util.HashMap<>();
map.put(new Key("ORD-7", 2), "done");
String result = map.get(new Key("ORD-7", 2)); // "done"
```

Đây là mảnh mã minh họa, không cần cùng tham chiếu key vì `equals` dùng giá trị. Nhưng record có `List` hoặc đối tượng mutable mà tham gia `equals`/`hashCode` có thể bị đổi hash khi nội dung thay đổi, khiến việc tìm lại khóa không còn tin cậy.

Đừng nhầm với collection có thứ tự: `TreeMap`/`TreeSet` dựa trên `Comparable`/`Comparator`. `record Point(int x,int y) {}` không tự triển khai `Comparable<Point>`; việc có `equals`/`hashCode` không tạo ra thứ tự tự nhiên. Muốn dùng sorted collection cần cung cấp comparator hoặc triển khai Comparable phù hợp.

## 7. Những lỗi và hiểu lầm điển hình

**“Hai record có cùng các trường thì phải bằng nhau.”** Chưa đủ. Với equality được tự sinh, **cùng chính xác record class** cũng là điều kiện bắt buộc; `Point(2,3)` khác `Coordinate(2,3)`.

**“Record tự so sâu toàn bộ thành phần tham chiếu.”** Sai. Nó dùng `equals` của thành phần. `String` so nội dung, `List` so phần tử theo hợp đồng List, còn mảng mặc định so identity. Với một kiểu do bạn viết mà không override `equals`, thành phần đó vẫn so identity.

**“Mọi record đều bất biến tuyệt đối.”** Sai. Các tham chiếu trường component là `final` nhưng đối tượng mà chúng trỏ đến có thể mutable. Đặc biệt mảng và danh sách thường yêu cầu sao chép phòng vệ nếu cần giá trị ổn định.

**“Record sử dụng `==` cho mọi primitive.”** Với `float`/`double`, equality tự sinh xử lý NaN và signed zero theo ngữ nghĩa như wrapper, khác toán tử `==` primitive. Test các giá trị biên trước khi tự cài `equals`.

**“Có equals rồi không cần hashCode.”** Nếu giữ cả hai phương thức tự sinh, Java đảm bảo tính tương thích. Nhưng khi tự override `equals` và bỏ qua `hashCode`, bạn có thể phá hợp đồng, nhất là nếu bỏ một component khỏi phép so sánh.

**“`toString` giống nhau đồng nghĩa đối tượng bằng nhau.”** `toString` nhằm hiển thị/debug, không là hợp đồng danh tính. Không dựa vào chuỗi in để thay `equals`, hoặc dùng thứ tự hiển thị để suy ra kết quả hash.

## 8. Khi cần equality khác mặc định: nên thiết kế thế nào?

Java cho phép khai báo tường minh `equals(Object)` và `hashCode()` trong record. Ví dụ, một object hiển thị sản phẩm có mã `sku` là khóa, còn `displayName` chỉ là dữ liệu bổ sung:

```java
import java.util.Objects;

record Product(String sku, String displayName) {
    Product {
        Objects.requireNonNull(sku);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Product p && sku.equals(p.sku));
    }

    @Override
    public int hashCode() {
        return sku.hashCode();
    }
}
```

Đây là một khai báo record Java 17 hợp lệ, chỉ là ví dụ về **tùy biến**; nó không còn so `displayName`. Hai `Product` cùng `sku` sẽ bằng nhau dù `displayName` khác. Cần giữ `equals`/`hashCode` dựa trên cùng khóa và dữ liệu khóa ổn định.

Nhưng khi mục tiêu chỉ là dùng mã sản phẩm làm khóa map, phương án đơn giản hơn thường là thiết kế `record ProductId(String sku) {}` riêng và lưu `displayName` trong một model khác. Như vậy không phải phá sự kỳ vọng mặc định rằng component của record xác định trạng thái giá trị của chính record.

Khi tự override equality, cần bảo vệ hợp đồng `Object`: phản xạ, đối xứng, bắc cầu, nhất quán, xử lý null và chiều suy ra giữa equals/hashCode. Đừng tùy tiện coi hai record class khác nhau là bằng nhau; phải xác định rõ ý nghĩa và kiểm chứng sự đối xứng giữa cả hai loại.

## 9. Checklist kiểm thử một record

1. Hai instance **cùng record class** và cùng tất cả component phải bằng nhau khi dùng phương thức tự sinh, dù khác tham chiếu.
2. Đổi một component thì kết quả phải thay đổi theo ngữ nghĩa equality của đúng kiểu component đó.
3. Hai **record class khác nhau** có cùng cấu trúc/dữ liệu vẫn không bằng nhau theo mặc định.
4. Thử component `null`, `String`, record lồng nhau, mảng và collection để hiểu kiểu nào so giá trị, kiểu nào so identity.
5. Kiểm tra `float`/`double` với NaN và hai signed zero; tránh áp dụng `==` primitive một cách máy móc.
6. Với component tham chiếu mutable, kiểm tra khả năng dữ liệu bị sửa sau khi tạo; dùng sao chép phòng vệ/bất biến khi làm khóa collection.
7. Hai record bằng nhau phải có cùng `hashCode()`; không đòi hỏi hash bằng nhau phải kéo theo record bằng nhau.
8. Dùng `HashSet`/`HashMap` với khóa mới cùng giá trị để xác minh tìm kiếm và loại trùng theo ý nghĩa nghiệp vụ.
9. Nếu tự viết `equals`, luôn xem xét lại `hashCode`, sự ổn định, phản xạ, đối xứng và bắc cầu; xem liệu có nên tạo record khóa riêng.
10. Nếu yêu cầu sắp xếp, xác định `Comparator` hoặc `Comparable` riêng, vì record không tự có thứ tự tự nhiên.

**Kết luận:** `equals(Object)` do Java tự sinh cho record trả `true` khi đối tượng kia **cùng chính xác record class** và **từng cặp component tương ứng bằng nhau**. Phần “bằng nhau” đến từ kiểu component: primitive, số thực, `String`, mảng và collection có những quy tắc khác nhau. Thiết kế đúng loại và tính ổn định của component quyết định record có thực sự là giá trị đáng tin cậy trong ứng dụng hay không.
