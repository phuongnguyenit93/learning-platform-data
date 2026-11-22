# Kiểu đầu vào, kiểu khóa và kiểu giá trị được suy luận trong Collector bản đồ

> **Ngữ cảnh Java 10 — Collector bản đồ.** Bài tập trung vào suy luận ba tham số kiểu `T`, `K`, `U` của `Collectors.toUnmodifiableMap`, kết quả `Map<K,U>` và cách phối hợp với `Stream.collect`, method reference, lambda, `var` và generic type inference. `toUnmodifiableMap` được bổ sung ở **Java 10**; các quy tắc generic và API này vẫn còn áp dụng trên những JDK hiện đại được nhà cung cấp hỗ trợ. Không cần cài Java 10 đã cũ để thực hành.

## 1. Mục tiêu cần đạt

Sau bài này, bạn có thể:

1. Đọc chữ ký `<T,K,U> Collector<T,?,Map<K,U>> toUnmodifiableMap(...)` và giải thích chính xác vai trò của **kiểu phần tử đầu vào**, **kiểu khóa**, **kiểu giá trị**.
2. Lần theo một pipeline `Stream<Row>` hoặc `Stream<String>` để xác định `T` **tại vị trí collect**, không tự động lấy kiểu từ danh sách ban đầu.
3. Suy ra `K` từ `keyMapper` và `U` từ `valueMapper`; biết primitive như `int` được boxing thành `Integer` trong tham số kiểu generic.
4. Dự đoán kiểu tĩnh của biến `var result = stream.collect(...)` và kiểm tra bằng phép gán `Map<K,U>` có chủ đích.
5. Giải thích tác dụng của overload có `BinaryOperator<U> mergeFunction` khi nhiều phần tử sinh cùng khóa.
6. Phân biệt collector unmodifiable Java 10 với `Collectors.toMap`, nhất là về tính có thể sửa, map supplier, `null` và thứ tự duyệt.
7. Nhận biết trường hợp suy luận kiểu thiếu ngữ cảnh khi **tách collector ra một biến `var` riêng**; sửa bằng method reference, lambda có kiểu tham số tường minh, type witness hoặc khai báo `Collector` tường minh.
8. Biên dịch, chạy và giải thích một chương trình hoàn chỉnh với output ổn định, không phụ thuộc thứ tự duyệt `Map`.

## 2. Bức tranh tổng thể: T ở đầu vào, K/U ở đầu ra

Một bản ghi có thể chứa nhiều thuộc tính. Ví dụ:

```java
// Ví dụ thành viên class, không phải tệp runnable riêng.
static final class Row {
    String code() { return "N1"; }
    String region() { return "north"; }
    int quantity() { return 2; }
}
```

Nếu đã có `List<Row> rows`, ta có thể xây map mã → số lượng:

```java
// Trong một phương thức có biến rows kiểu List<Row>.
var byCode = rows.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                Row::code, Row::quantity));
```

Trong lời gọi này:

- `rows.stream()` là `Stream<Row>`, nên **`T = Row`**.
- `Row::code` nhận một `Row` và trả `String`, nên **`K = String`**.
- `Row::quantity` nhận một `Row` và trả `int`; khi dùng làm giá trị trong `Map`, kiểu primitive được boxing, nên **`U = Integer`**.
- Kết quả cuối là **`Map<String,Integer>`**. Vì dùng `var`, kiểu tĩnh của `byCode` được suy ra từ biểu thức `collect(...)` chính là `Map<String,Integer>`.

Có thể kiểm tra bằng phép gán không cần chạy:

```java
Map<String, Integer> proof = byCode; // Hợp lệ.
```

`proof` không chuyển đổi map sang một kiểu khác; nó chỉ chứng minh quan hệ kiểu tại lúc biên dịch. Một phép gán `Map<Integer,String> wrong = byCode;` sẽ bị compiler từ chối vì thứ tự và type arguments không khớp.

**Ghi nhớ:** `T` không phải kiểu khóa, `K` không nhất thiết là `String` và `U` không bắt buộc trùng kiểu `T`. Một `Row` có thể biến thành `Map<Integer,String>` bằng cách đổi hai mapper; kiểu đầu vào vẫn `Row`.

## 3. Đọc đúng chữ ký generic trong Javadoc

Các chữ ký khái quát của `java.util.stream.Collectors`:

```java
public static <T, K, U>
Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper);

public static <T, K, U>
Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction);
```

Hai phương thức cùng tên nhưng khác số tham số, đều có từ Java 10. Trong Javadoc:

| Ký hiệu | Vai trò | Với `Stream<Row>` và hai mapper `Row::code`, `Row::quantity` |
| --- | --- | --- |
| `T` | Kiểu **đầu vào** của collector — mỗi phần tử Stream đi vào quá trình gom | `Row` |
| `K` | Kiểu **khóa** do `keyMapper` tạo | `String` |
| `U` | Kiểu **giá trị** do `valueMapper` tạo | `Integer` |
| `Function<? super T, ? extends K>` | Hàm nhận loại đối số tương thích với `T` và cho kết quả tương thích với `K` | `Row::code` |
| `Function<? super T, ? extends U>` | Hàm nhận loại đối số tương thích với `T` và cho kết quả tương thích với `U` | `Row::quantity` (boxing từ `int`) |
| `BinaryOperator<U>` | Hàm kết hợp **hai giá trị `U`** khi cùng key; không kết hợp hai key | `Integer::sum` nếu `U=Integer` |
| `Collector<T,?,Map<K,U>>` | Collector nhận phần tử `T`, dùng accumulator nội bộ ẩn bởi wildcard `?`, xuất `Map<K,U>` | `Collector<Row,?,Map<String,Integer>>` |

### Ý nghĩa của `? super T` và `? extends K/U`

`Function<? super T, ? extends K>` thể hiện tính linh hoạt của functional interface:
- Phần đầu vào có thể chấp nhận `T` hoặc **một kiểu cha phù hợp của `T`**.
- Kết quả có thể là `K` hoặc **một subtype phù hợp với `K`**.

Tương tự với value mapper. Không diễn giải wildcard thành việc key hoặc value “không có kiểu”. Compiler vẫn phải giải các ràng buộc generic cụ thể để hoàn tất lời gọi.

Ví dụ `Row::quantity` trả primitive `int`, nhưng `Map<K,U>` không thể nhận primitive làm generic type argument, nên `U` là `Integer`. Điều này khác với `IntStream` nơi phép toán có thể sử dụng `int` nguyên thủy trong nhiều giai đoạn.

### Tại sao có `?` trong `Collector<T, ?, Map<K,U>>`?

Tham số kiểu giữa của `Collector<T,A,R>` là **kiểu vùng tích lũy trung gian** `A` (accumulation type), không phải key/value. Javadoc che giấu chi tiết `A` bằng `?` vì code sử dụng không cần biết collector gom dữ liệu bằng loại container nội bộ nào. Người đọc không nên thay `?` thành `Map`, `HashMap` hoặc suy luận implementation của collector từ đó.

## 4. Từng bước suy luận kiểu khi gọi `collect`

Hãy đọc một biểu thức như một luồng thông tin đi qua các chặng, thay vì đoán từ tên biến.

### Bước 1 — Xác định `Stream<T>` ngay trước `collect`

```java
List<Row> rows = ...;               // T của nguồn dữ liệu: Row
Stream<Row> input = rows.stream();   // T của Stream: Row
```

Đây là mã minh họa có ký hiệu `...` và không chạy độc lập. Trong ứng dụng, `rows` có thể được tạo từ API, constructor hoặc phương thức nội bộ. Nếu không biết chữ ký của nguồn dữ liệu, phải tìm đúng khai báo trước khi kết luận.

`filter` không thay kiểu phần tử:

```java
rows.stream().filter(r -> r.quantity() > 0)
```

Kết quả vẫn là `Stream<Row>`. Nhưng `map(Row::code)` biến thành `Stream<String>`. Vì thế **`T` được lấy từ Stream sau các phép biến đổi, không phải luôn từ List ban đầu**.

### Bước 2 — Xác định `K` theo key mapper

Với `Stream<Row>`:

```java
Row::code      // Row -> String: K = String
Row::quantity  // Row -> int, boxing: K = Integer
Row::region    // Row -> String: K = String
```

Đây là các method references chỉ có ý nghĩa khi class `Row` đã khai báo chữ ký tương ứng. Nếu key mapper là một lambda:

```java
row -> row.region().toUpperCase(java.util.Locale.ROOT)
```

thì kết quả là `String`, nên `K=String`. Nếu key mapper trả một enum, `K` có thể là enum đó; không nên cố chuyển tất cả keys sang chuỗi chỉ vì ví dụ dùng chuỗi.

### Bước 3 — Xác định `U` theo value mapper

```java
Row::quantity                     // int -> Integer
Row::code                         // String
row -> (long) row.quantity()      // long -> Long
row -> (Number) row.quantity()    // cast/boxing -> Number
```

`U` được suy luận từ **kiểu biểu thức trả về**, không nhất thiết từ class thực tế ở runtime. Ở ví dụ cuối, value có kiểu tĩnh `Number` do cast, mặc dù object được boxing bên trong có thể là `Integer`.

### Bước 4 — Nếu có merge function, kiểm tra kiểu `U` của nó

```java
Collectors.toUnmodifiableMap(
        Row::region,
        Row::quantity,
        Integer::sum)
```

`Row::quantity` làm `U=Integer`. `Integer::sum` nhận hai `int`, trả `int` và phù hợp với `BinaryOperator<Integer>` thông qua unboxing/boxing. Nó hợp nhất giá trị cho các `Row` có cùng region. Nếu muốn lưu `Long`, phải thiết kế value mapper và hàm merge phù hợp với `Long`, ví dụ:

```java
Collectors.toUnmodifiableMap(
        Row::region,
        row -> (long) row.quantity(),
        Long::sum)
```

Khi đó `K=String` và `U=Long`. Đừng dùng `Integer::sum` như hàm merge cho một collector đã suy luận `U=Long`.

### Bước 5 — Ghép kết quả collector với `Stream.collect`

`Stream.collect(Collector<? super T,A,R>)` tạo kết quả kiểu `R`. Với collector `Collector<Row,?,Map<String,Integer>>`, `R` là `Map<String,Integer>`. Đây chính là kiểu mà compiler dùng cho:

```java
var totals = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, Row::quantity, Integer::sum));
// totals: Map<String, Integer>
```

`var` là **suy luận kiểu biến cục bộ tại compile time**, không phải kiểu động. Nó không khiến `Map` tự thay kiểu key/value khi có các lần gọi `put` về sau. Hơn nữa, vì collector tạo map không cho sửa, `put` trên kết quả sẽ ném `UnsupportedOperationException` khi chạy.

## 5. Chương trình Java đầy đủ: quan sát T, K, U và ngoại lệ

Sử dụng JDK **đang được nhà cung cấp hỗ trợ và cập nhật bảo mật** (chẳng hạn JDK 21/25 LTS của bản phân phối phù hợp), không cần cài JDK 10 đã lỗi thời. Các API trong lab có mặt từ Java 10 hoặc trước đó; class `Row` dùng cú pháp class thông thường để giữ ví dụ tương thích.

### 5.1. Chuẩn bị

```bash
java -version
javac -version
```

Tạo tệp **`MapCollectorInferenceLab.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MapCollectorInferenceLab {
    static final class Row {
        private final String code;
        private final String region;
        private final int quantity;

        Row(String code, String region, int quantity) {
            this.code = code;
            this.region = region;
            this.quantity = quantity;
        }

        String code() { return code; }
        String region() { return region; }
        int quantity() { return quantity; }
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(
                new Row("N1", "north", 2),
                new Row("S2", "south", 3),
                new Row("N3", "north", 5));

        // T=Row; K=String; U=Integer (boxing từ int).
        var byCode = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::code, Row::quantity));
        Map<String, Integer> verified = byCode;
        System.out.println(
                "code N3 quantity: " + verified.get("N3"));

        // Đổi vai trò hai mapper: K=Integer, U=String.
        var byQuantity = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::quantity, Row::code));
        Map<Integer, String> quantityProof = byQuantity;
        System.out.println(
                "quantity 3 code: " + quantityProof.get(3));

        // Hai Row có region "north": cần merge giá trị U=Integer.
        var byRegion = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::region, Row::quantity, Integer::sum));
        System.out.println(
                "north total: " + byRegion.get("north"));

        var countByRegion = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::region, row -> 1, Integer::sum));
        System.out.println(
                "north rows: " + countByRegion.get("north"));

        // Stream<Row> -> map(Row::code) -> Stream<String>.
        // T mới = String; K=String; U=Integer.
        var codeLengths = rows.stream().map(Row::code)
                .collect(Collectors.toUnmodifiableMap(
                        Function.identity(), String::length));
        Map<String, Integer> lengthsProof = codeLengths;
        System.out.println(
                "code N1 length: " + lengthsProof.get("N1"));

        // U thay đổi theo kiểu của value mapper.
        var upcast = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::code, row -> (Number) row.quantity()));
        Map<String, Number> numberProof = upcast;
        System.out.println("number type: "
                + numberProof.get("N1").getClass().getSimpleName());

        var longs = rows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Row::code, row -> (long) row.quantity()));
        Map<String, Long> longProof = longs;
        System.out.println("long type: "
                + longProof.get("N1").getClass().getSimpleName());

        // Tách collector ra một biến có khai báo generic tường minh.
        Collector<Row, ?, Map<String, Integer>> explicitCollector =
                Collectors.toUnmodifiableMap(
                        Row::code, Row::quantity);
        var witnessCollector =
                Collectors.<Row, String, Integer>toUnmodifiableMap(
                        Row::code, Row::quantity);
        Collector<Row, ?, Map<String, Integer>> checked =
                witnessCollector;

        System.out.println("collector result size: "
                + rows.stream().collect(explicitCollector).size());
        System.out.println("witness empty size: "
                + Stream.<Row>empty().collect(checked).size());

        // Với hai method reference này, compiler cũng suy luận được
        // ba type arguments khi không có target từ vế trái var.
        var directCollector = Collectors.toUnmodifiableMap(
                Row::code, Row::quantity);
        Collector<Row, ?, Map<String, Integer>> directProof =
                directCollector;
        System.out.println("isolated collector size: "
                + rows.stream().collect(directProof).size());

        try {
            rows.stream().collect(Collectors.toUnmodifiableMap(
                    Row::region, Row::quantity));
        } catch (IllegalStateException ex) {
            System.out.println(
                    "duplicate region: IllegalStateException");
        }

        // Mỗi tình huống null dùng 1 Row, tránh gộp nhiều lỗi
        // khiến thứ tự ném exception phụ thuộc đường thực thi.
        try {
            rows.stream().limit(1).collect(
                    Collectors.toUnmodifiableMap(
                            row -> (String) null, Row::quantity));
        } catch (NullPointerException ex) {
            System.out.println("null key: NullPointerException");
        }

        try {
            rows.stream().limit(1).collect(
                    Collectors.toUnmodifiableMap(
                            Row::code, row -> (Integer) null));
        } catch (NullPointerException ex) {
            System.out.println("null value: NullPointerException");
        }

        try {
            byCode.put("X", 99);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "unmodifiable: UnsupportedOperationException");
        }

        // Khi cần map mutable với implementation rõ ràng:
        // overload toMap có mapFactory.
        var editable = rows.stream()
                .collect(Collectors.toMap(
                        Row::code, Row::quantity,
                        (left, right) -> left,
                        LinkedHashMap::new));
        LinkedHashMap<String, Integer> editableProof = editable;
        editableProof.put("X", 99);
        System.out.println("editable X: " + editableProof.get("X"));
    }
}
```

Biên dịch và chạy:

```bash
javac MapCollectorInferenceLab.java
java MapCollectorInferenceLab
```

### 5.2. Stdout chính xác (15 dòng)

```text
code N3 quantity: 5
quantity 3 code: S2
north total: 7
north rows: 2
code N1 length: 2
number type: Integer
long type: Long
collector result size: 3
witness empty size: 0
isolated collector size: 3
duplicate region: IllegalStateException
null key: NullPointerException
null value: NullPointerException
unmodifiable: UnsupportedOperationException
editable X: 99
```

Lab không in nguyên một `Map`, nên không phụ thuộc vào thứ tự iteration không được Javadoc bảo đảm. Các bản ghi được chọn có khóa riêng cho các trường hợp không merge; trường hợp `region="north"` cố tình trùng để quan sát luật duplicate key.

### 5.3. Giải thích output

1. **`byCode`:** `T=Row`, `K=String` do `Row::code`, `U=Integer` do `Row::quantity`. `"N3"` gắn số lượng `5`.
2. **`byQuantity`:** hoán đổi mapper làm `K=Integer`, `U=String`. Khóa `3` gắn mã `S2`. Hai mapper không mang vai trò cố định ngoài vị trí tham số của `toUnmodifiableMap`.
3. **`byRegion`:** có hai dòng `north` với số lượng `2` và `5`. `Integer::sum` kết hợp thành `7`. `countByRegion` lại map mỗi dòng thành `1`, nên tổng dòng `north` là `2`. Cùng `K=String` và `U=Integer` nhưng **ý nghĩa value mapper** hoàn toàn khác.
4. **`codeLengths`:** đầu vào ở điểm `collect` là `Stream<String>` vì đã `map(Row::code)`. `Function.identity()` giữ code làm key, `String::length` trả `int` rồi boxing thành `Integer`. `"N1"` có độ dài `2`.
5. **`upcast` và `longs`:** kiểu map value khác nhau (`Number` so với `Long`). Dòng `number type: Integer` phản ánh **loại object được boxing trong ví dụ**, không thay đổi sự thật `upcast` có kiểu tĩnh `Map<String,Number>`. `longs` giữ value kiểu tĩnh `Long`.
6. **Collector viết riêng:** có thể cố định `T,K,U` bằng khai báo `Collector<Row,?,Map<String,Integer>>` hoặc type witness `Collectors.<Row,String,Integer>toUnmodifiableMap(...)`. Với method references đủ thông tin trong trường hợp này, `var directCollector = ...` cũng suy luận được.
7. **Duplicate key:** khi không có merge function, `Row::region` tạo hai key `north` bằng nhau. Collector hai tham số từ chối bằng `IllegalStateException`.
8. **Null:** cả null key và null value đều không được phép ở `toUnmodifiableMap`. Lab dùng từng stream một phần tử và bắt `NullPointerException`, không cần dựa vào chi tiết exception message của JDK.
9. **Unmodifiable:** `byCode.put` ném `UnsupportedOperationException`. Kết quả `toUnmodifiableMap` là map không cho sửa, không phải map có thể sửa chỉ vì biến được khai báo `var`.
10. **Map có supplier:** overload `Collectors.toMap(..., LinkedHashMap::new)` tạo `LinkedHashMap<String,Integer>` theo map factory. `editable.put("X",99)` hợp lệ; điều này **không** đồng nghĩa collector `toUnmodifiableMap` có overload nhận map factory.

## 6. Suy luận kiểu qua method reference, lambda và collector tách riêng

### 6.1. Trường hợp sử dụng inline: có `Stream<T>` cung cấp ngữ cảnh

```java
var map = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                row -> row.code(),
                row -> row.quantity()));
```

Vì `rows.stream()` là `Stream<Row>`, Java có ngữ cảnh để hiểu các tham số `row` của lambda là `Row`. Kiểu kết quả là `Map<String,Integer>`. Đây là một ví dụ *poly expression*/target typing trong lời gọi phương thức: dù vế trái có `var`, **các biểu thức con** vẫn nhận target type từ tham số của `collect` và `toUnmodifiableMap`.

Không nên diễn giải rằng `var` làm mọi lambda trong initializer không hợp lệ. `var fn = x -> x.toString();` **trực tiếp** làm initializer là lỗi do thiếu target functional interface, nhưng lambda **ở vị trí tham số một phương thức đã có chữ ký** có thể hoàn toàn hợp lệ.

### 6.2. Tách collector với method reference có thể vẫn suy luận được

Trong lab:

```java
var directCollector = Collectors.toUnmodifiableMap(
        Row::code, Row::quantity);
Collector<Row, ?, Map<String, Integer>> proof =
        directCollector; // Hợp lệ.
```

Method references `Row::code` và `Row::quantity` có thông tin đủ về receiver và return type để compiler giải các ràng buộc generic trong tình huống cụ thể này. Không có quy tắc “cứ tách collector ra `var` là suy luận thất bại”.

### 6.3. Tách collector với lambda thiếu kiểu có thể không biên dịch

Đoạn sau **cố ý sai** và không thuộc tệp lab:

```java
var collector = Collectors.toUnmodifiableMap(
        row -> row.code(),
        row -> row.quantity()); // Lỗi: compiler không biết row phải là kiểu gì.
```

Khi chưa có `Stream<Row>`, collector không có thông tin đầu vào đủ rõ để suy luận `row` từ các lambda có tham số không chỉ rõ kiểu. Compiler không thể chỉ nhìn lời gọi `row.code()` rồi tự đoán class `Row` trong toàn bộ chương trình.

Ba cách sửa:

```java
// Cách 1: khai báo kiểu generic rõ cho biến collector.
Collector<Row, ?, Map<String, Integer>> collector1 =
        Collectors.toUnmodifiableMap(
                row -> row.code(), row -> row.quantity());

// Cách 2: thêm type witness tại phương thức generic.
var collector2 = Collectors.<Row, String, Integer>toUnmodifiableMap(
        row -> row.code(), row -> row.quantity());

// Cách 3: khai báo kiểu tham số lambda.
var collector3 = Collectors.toUnmodifiableMap(
        (Row row) -> row.code(),
        (Row row) -> row.quantity());
```

Đây là các **đoạn minh họa nằm trong một class/method** có sẵn định nghĩa `Row` và imports `Collectors`, `Collector`, `Map`. Không sao chép nguyên các đoạn trên thành ba file Java riêng lẻ thiếu class/imports.

Một cách khác là viết collector inline trong `rows.stream().collect(...)`, khi đó kiểu `Stream<Row>` cung cấp ngữ cảnh cho lambda không ghi kiểu.

### 6.4. Không suy luận từ thứ tự sử dụng biến về sau

```java
var codes = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::code, Row::quantity));
// Map<String,Integer>, được xác định ngay ở dòng trên.

// Điều này không làm codes đổi kiểu:
Number value = codes.get("N1");
```

Phép gán `Number value = ...` hợp lệ vì `Integer` là subtype của `Number`. Nhưng kiểu tĩnh của `codes` **vẫn** là `Map<String,Integer>`, không chuyển thành `Map<String,Number>` theo một lệnh sử dụng về sau.

Generic type arguments là bất biến (*invariant*): `Map<String,Integer>` **không phải subtype** của `Map<String,Number>`, dù `Integer extends Number`. Nếu muốn kiểu value tĩnh là `Number`, phải cấp thông tin tương ứng trong phép suy luận hoặc khai báo API ngay tại điểm xây collector, như `row -> (Number) row.quantity()`.

## 7. Những biến đổi làm thay đổi T, K hoặc U

### 7.1. Thay Stream element type ⇒ thay T

```java
// rows: List<Row>
var mapA = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::code, Row::quantity));
// T=Row; K=String; U=Integer

var mapB = rows.stream()
        .map(Row::code)
        .collect(Collectors.toUnmodifiableMap(
                Function.identity(), String::length));
// T=String; K=String; U=Integer
```

Dù cả hai có thể xuất `Map<String,Integer>`, chúng gom dữ liệu từ hai loại phần tử khác nhau (`Row` và `String`), và ý nghĩa số nguyên cũng khác (số lượng và độ dài mã). Phải xác định `T` theo bước cuối trước `collect`.

### 7.2. Đổi key mapper ⇒ thay K

```java
var byCode = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::code, Row::quantity));
// Map<String,Integer>

var byQuantity = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::quantity, Row::code));
// Map<Integer,String>
```

Đây không phải chỉ đổi tên biến. Kết quả đã đảo cả **kiểu khóa**, **kiểu giá trị** lẫn ý nghĩa tra cứu. Vì `Row::quantity` là `int`, `Integer` được dùng làm generic key type.

**Cảnh báo:** nếu số lượng trùng (ví dụ hai `Row` có `quantity==2`), phép tạo `byQuantity` hai tham số sẽ ném `IllegalStateException` vì duplicate key. Bản lab chọn quantity 2,3,5 khác nhau để tránh nhầm lỗi suy luận kiểu với lỗi dữ liệu trùng.

### 7.3. Đổi value mapper ⇒ thay U

```java
var intAmounts = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::code, Row::quantity));
// Map<String,Integer>

var longAmounts = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::code, row -> (long) row.quantity()));
// Map<String,Long>

var numberAmounts = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::code, row -> (Number) row.quantity()));
// Map<String,Number>
```

Khi sử dụng `var`, reviewer phải nhìn **toàn bộ expression** ở vế phải, không đoán generic type từ tên biến. Trong ví dụ `numberAmounts`, phép cast làm thay đổi **kiểu tĩnh** giá trị; nó không biến object Integer thành loại đối tượng Number mới.

### 7.4. Suy luận từ kiểu đích explicit và type witness

```java
Map<String, Number> typed = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::code, row -> (Number) row.quantity()));

var witnessed = rows.stream()
        .collect(Collectors.<Row, String, Number>toUnmodifiableMap(
                Row::code, row -> row.quantity()));
```

Dòng đầu khai báo rõ hợp đồng `Map<String,Number>` và value mapper đã cho kết quả kiểu `Number`. Dòng thứ hai chỉ định type witness `<Row,String,Number>`; kết quả `Integer` từ mapper có thể được dùng tại vị trí mong đợi `Number`. Không cần ép kiểu mỗi giá trị nếu ràng buộc generic đã diễn đạt rõ ý định.

Tránh type witness dài nếu initializer đã tự rõ kiểu; dùng nó khi cần giữ hợp đồng API hoặc giải quyết trường hợp suy luận thiếu thông tin.

## 8. Duplicate keys: chính sách nghiệp vụ khác với kiểu K

### 8.1. Hai đối số: trùng khóa là lỗi

```java
var byRegion = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, Row::quantity));
```

`Row::region` trả `String` nên `K=String`. Vì hai bản ghi cùng có `region="north"`, collector báo **`IllegalStateException`** lúc collect. Đây là lỗi dữ liệu/quy tắc duplicate keys, **không phải lỗi suy luận generic**. Hai mapper vẫn có kiểu hợp lệ khi biên dịch.

### 8.2. Ba đối số: merge là phép toán trên U

```java
var totals = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, Row::quantity, Integer::sum));
```

`Integer::sum` có nhiệm vụ kết hợp `2` và `5` cho cùng key thành `7`. Nó nhận **hai giá trị `U`** và trả một giá trị `U` mới. Nó không nhận hai đối tượng `Row` và cũng không chọn region.

Nếu muốn đếm số dòng, value mapper có thể trả số `1`:

```java
var counts = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, row -> 1, Integer::sum));
```

Khi đó `counts.get("north") == 2`. Đừng nhầm tổng số lượng `7` với số dòng `2`; type arguments giống nhau nhưng ngữ nghĩa mapper khác.

### 8.3. Cẩn thận với xử lý song song

Nếu dùng `parallelStream()`, phép merge có thể được thực hiện theo cấu trúc phân chia/gộp khác. Chọn hàm merge **kết hợp được** (*associative*) và không có side effects khi có thể; `Integer::sum` là minh họa phù hợp. Không dựa vào “phần tử nào được xử lý trước” để quyết định winner trong các đoạn parallel không được thiết kế chính sách thứ tự rõ ràng.

Muốn ưu tiên first/last hoặc chọn theo timestamp, hãy biểu diễn quy tắc rõ ràng, kiểm tra cách xử lý ordered stream và chi phí song song. Chỉ viết `(a,b)->a` mà không hiểu encounter order có thể cho kết quả không đúng yêu cầu nghiệp vụ.

## 9. So sánh các collector bản đồ vẫn dùng hiện nay

| API | Kiểu kết quả | Xử lý key trùng | Mutability / mục đích |
| --- | --- | --- | --- |
| `toUnmodifiableMap(keyMapper, valueMapper)` (Java 10) | `Map<K,U>` | `IllegalStateException` nếu key trùng | Kết quả **không cho sửa**, từ chối null keys/values. |
| `toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` (Java 10) | `Map<K,U>` | Merge các giá trị `U` | Kết quả **không cho sửa**, từ chối null. |
| `toMap(keyMapper, valueMapper)` | `Map<K,U>` | Mặc định ném lỗi nếu key trùng | API không cam kết concrete type, mutability, iteration order hay thread safety. |
| `toMap(keyMapper, valueMapper, mergeFunction)` | `Map<K,U>` | Merge các giá trị `U` | Không cam kết concrete type/mutability. |
| `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` | `M extends Map<K,U>` | Merge theo hàm cung cấp | Có thể chọn concrete map supplier, ví dụ `LinkedHashMap::new`. |
| `groupingBy(classifier)` | `Map<K,List<T>>` | Gom nhiều `T` vào cùng `List` cho mỗi key | Phù hợp khi cần giữ **tất cả các phần tử trong từng nhóm**, khác merge thành một `U` duy nhất. |

### 9.1. Khi nào dùng `groupingBy` thay vì `toUnmodifiableMap`?

Giả sử cần **tất cả Row** của mỗi region, không phải tổng số lượng:

```java
var groups = rows.stream().collect(
        Collectors.groupingBy(Row::region));
// Map<String, List<Row>>
```

Ở đây kiểu value là **`List<Row>`**, không phải `Integer`. Nếu nghiệp vụ muốn công bố kết quả không cho sửa cả lớp map lẫn các danh sách con, cần thiết kế **deep-enough defensive snapshot** cho các container lồng nhau; chỉ bọc map ngoài không làm mọi `List` bên trong bất biến.

Khi cần tổng số lượng, collector `toUnmodifiableMap(Row::region, Row::quantity, Integer::sum)` trực tiếp hơn và có kiểu `Map<String,Integer>`.

### 9.2. Khi nào cần map factory?

Nếu cần kết quả **có thể sửa** và biết chắc implementation:

```java
var mutableIndex = rows.stream().collect(
        Collectors.toMap(
                Row::code,
                Row::quantity,
                (previous, current) -> previous,
                java.util.LinkedHashMap::new));
```

Đây là overload có tham số `Supplier<M>`. Với `LinkedHashMap::new`, `M` được suy luận thành `LinkedHashMap<String,Integer>`; caller có thể cập nhật map kết quả. Không cho rằng collector `toUnmodifiableMap` hỗ trợ map factory — nó **không có** overload tương ứng.

Nếu chỉ dùng `Collectors.toMap(keyMapper,valueMapper)`, Javadoc không bảo đảm kết quả luôn là `HashMap` hoặc luôn mutable. Khi khả năng sửa là một phần của hợp đồng, hãy chọn collector có map factory phù hợp hoặc tạo một bản copy mutable theo yêu cầu.

## 10. Sai sót dễ gặp khi suy luận T, K, U

| Sai sót | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Đồng nhất `T` với `K` hoặc `U` | `T` là kiểu phần tử Stream, `K/U` là kiểu **kết quả** của mapper. | Ghi rõ `Stream<T>` và chữ ký hai mapper trước khi kết luận. |
| Lấy `T` từ List nguồn sau khi có `map(...)` | `map` có thể đổi `Stream<Row>` thành `Stream<String>`. | Lần theo từng bước, lấy `T` ngay trước `collect`. |
| Viết `Map<String,int>` | Java generics không nhận primitive. | Dùng `Map<String,Integer>`, để boxing hoặc map giá trị khác có chủ ý. |
| Tưởng `var` làm kiểu Map động | `var` suy luận kiểu tĩnh từ initializer. | Kiểm tra kiểu qua phép gán tường minh khi cần. |
| Tưởng mọi collector tách riêng với `var` đều lỗi | Method reference có thể đủ thông tin suy luận kiểu. | Đánh giá đúng dạng mapper, type witness và target type sẵn có. |
| Tách `var collector = toUnmodifiableMap(x->x.code(),...)` mà không cho biết loại `x` | Không có kiểu Stream cung cấp target cho lambda; compiler không suy từ tên method. | Khai báo `Collector<Row,...>`, type witness hoặc kiểu lambda tường minh. |
| Dùng `Integer::sum` khi `U` là `Long` | Chữ ký merge phải phù hợp `BinaryOperator<U>`. | Dùng `Long::sum` và value mapper trả `Long`. |
| Không xử lý duplicate keys | Hai phần tử có cùng `K` gây `IllegalStateException` ở overload hai tham số. | Dùng merge function theo hợp đồng hoặc kiểm tra trùng trước. |
| Cho mapper trả null | `toUnmodifiableMap` từ chối null key/value. | Validate/filter hoặc biểu diễn thiếu dữ liệu theo hợp đồng; không trộn nhiều lỗi vào một case test. |
| Gọi `put` lên map từ `toUnmodifiableMap` | Map kết quả không cho sửa. | Dùng `toMap` với supplier mutable khi cần cập nhật. |
| Chụp `Map.toString()` rồi assert thứ tự keys | Không có hợp đồng iteration order cho map unmodifiable. | Test `get(key)`, `size()`, `containsKey` và kiểu tĩnh. |
| Nghĩ unmodifiable là deep immutable | Value objects bên trong map có thể mutable. | Dùng immutable values/defensive copy nếu cần ảnh chụp ổn định. |

### Suy luận kiểu không thay thế kiểm tra dữ liệu

Ngay cả khi code có kiểu `Map<String,Integer>` hoàn toàn đúng, một nguồn dữ liệu có hai dòng cùng code vẫn có thể làm collector ném `IllegalStateException`. Ngược lại, một mapper tạo giá trị số học phù hợp nhưng `null` ở một code có thể gây `NullPointerException`. Suy luận kiểu giải quyết **tính tương thích lúc biên dịch**; duplicate/null là **ràng buộc khi chạy**.

Đừng lạm dụng ép kiểu chỉ để khiến compiler hài lòng. Một cast `(Number) row.quantity()` có thể đúng nếu API yêu cầu `Map<String,Number>`, nhưng dùng nó không hợp lý có thể che một hợp đồng dữ liệu chưa rõ.

## 11. Bài tập luyện xác định ba kiểu (có đáp án)

### Bài 1 — Đọc đơn giản

Với `List<Row> rows` và `Row.code():String`, `Row.quantity():int`:

```java
var map = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::code, Row::quantity));
```

**Đáp án:** `T=Row`; `K=String`; `U=Integer` (boxing từ `int`). Kiểu tĩnh của `map` là `Map<String,Integer>`, kết quả không cho sửa.

### Bài 2 — Đảo hai mapper

```java
var map = rows.stream().collect(
        Collectors.toUnmodifiableMap(Row::quantity, Row::code));
```

**Đáp án:** `T=Row`; `K=Integer`; `U=String`; kết quả `Map<Integer,String>`. Cần bảo đảm quantity không trùng, hoặc chọn merge function.

### Bài 3 — `map(...)` trước `collect`

```java
var lengths = rows.stream().map(Row::code).collect(
        Collectors.toUnmodifiableMap(
                Function.identity(), String::length));
```

**Đáp án:** `T=String` vì `map(Row::code)` đã biến Stream; `K=String` từ identity; `U=Integer` từ `String::length` (trả `int`). Kết quả `Map<String,Integer>`. Phân biệt đầu vào `T` với kiểu của `List<Row>` gốc.

### Bài 4 — Trùng khóa vùng

Hai Row có region `north` với quantity 2 và 5:

```java
var totals = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, Row::quantity, Integer::sum));
```

**Đáp án:** `Map<String,Integer>`; `totals.get("north")==7`. Nếu xóa `Integer::sum`, lời gọi có thể biên dịch nhưng ném `IllegalStateException` khi gặp hai key `north`.

### Bài 5 — Thay kiểu U từ Integer sang Long

```java
var totals = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region,
                row -> (long) row.quantity(),
                Long::sum));
```

**Đáp án:** `T=Row`, `K=String`, `U=Long`, kết quả `Map<String,Long>`. `Long::sum` phù hợp với kiểu value. Không thay bằng `Integer::sum` khi `U=Long`.

### Bài 6 — Suy luận collector ở biến riêng

Cho:

```java
var collector = Collectors.toUnmodifiableMap(
        row -> row.code(), row -> row.quantity());
```

**Đáp án:** Đây là ví dụ thiếu thông tin kiểu của tham số lambda `row` nếu không có target type từ ngữ cảnh ngoài. Có thể sửa bằng:

```java
Collector<Row, ?, Map<String, Integer>> collector =
        Collectors.toUnmodifiableMap(
                row -> row.code(), row -> row.quantity());
```

hoặc `Collectors.<Row,String,Integer>toUnmodifiableMap(...)`. Nếu đổi thành method references `Row::code`, `Row::quantity`, compiler có thể suy ra trong trường hợp này ngay cả với biến `var`.

### Bài 7 — Kiểu object runtime không phải U

```java
var map = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::code, row -> (Number) row.quantity()));
```

**Đáp án:** `U=Number`; `map` là `Map<String,Number>`. Những value được boxing có thể là `Integer` ở runtime, nhưng không vì vậy mà kiểu tĩnh của map là `Map<String,Integer>`.

### Bài 8 — Lỗi null

```java
var one = rows.stream().limit(1).collect(
        Collectors.toUnmodifiableMap(
                row -> (String) null, Row::quantity));
```

**Đáp án:** Lời gọi có thể biên dịch và có dạng `Map<String,Integer>` về kiểu tĩnh, nhưng ném `NullPointerException` vì key mapper trả null. Không sửa bằng cast khác để “né” null; phải xử lý dữ liệu đầu vào hay quy tắc null đúng nghiệp vụ.

### Bài 9 — Chọn map mutable có thứ tự chèn

Yêu cầu một `LinkedHashMap<String,Integer>` để còn `put` và để giữ thứ tự chèn. Chọn collector:

```java
var map = rows.stream().collect(
        Collectors.toMap(
                Row::code, Row::quantity,
                (previous, current) -> previous,
                java.util.LinkedHashMap::new));
```

**Đáp án:** Overload `toMap` có supplier cho `M extends Map<K,U>`; `M` suy luận là `LinkedHashMap<String,Integer>`. Đó là lựa chọn khác với `toUnmodifiableMap` khi cần chỉnh sửa kết quả.

### Bài 10 — Nhìn kiểu nhưng đừng đoán ý nghĩa

```java
var totals = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, Row::quantity, Integer::sum));
var counts = rows.stream().collect(
        Collectors.toUnmodifiableMap(
                Row::region, row -> 1, Integer::sum));
```

**Đáp án:** Cả hai đều là `Map<String,Integer>`. Nhưng `totals.get("north")==7` và `counts.get("north")==2`. **Kiểu suy luận giống nhau không đồng nghĩa ý nghĩa nghiệp vụ giống nhau**; phải đọc logic của value mapper.

## 12. Checklist review trước khi dùng collector bản đồ

- [ ] Xác định `Stream<T>` ở ngay trước `collect`, sau mọi `filter/map/flatMap`.
- [ ] Đọc kiểu trả về của `keyMapper` để xác định `K`.
- [ ] Đọc kiểu trả về của `valueMapper` để xác định `U`, kể cả boxing primitive.
- [ ] Hiểu `Collector<T,?,Map<K,U>>`: wildcard giữa không đại diện kiểu khóa/giá trị.
- [ ] Phân biệt kết quả `Map<K,U>` của `toUnmodifiableMap` với kiểu map có supplier `M` của `toMap`.
- [ ] Không nhầm `var` là kiểu động; kiểm tra phép gán `Map<K,U>` nếu muốn chứng minh kiểu.
- [ ] Khi tách collector riêng, bảo đảm lambda có ngữ cảnh kiểu hoặc dùng method reference/type witness/khai báo tường minh.
- [ ] Nếu key có thể trùng, lựa chọn báo lỗi hay merge rõ ràng và đúng `U`.
- [ ] Không để mapper trả null khi sử dụng `toUnmodifiableMap`.
- [ ] Không gọi thao tác sửa trên kết quả unmodifiable.
- [ ] Không dựa vào thứ tự duyệt map hoặc concrete implementation không được Javadoc bảo đảm.
- [ ] Khi dùng parallel stream, chọn hàm merge kết hợp được và không có side effects.
- [ ] Chạy `MapCollectorInferenceLab.java` và đối chiếu đúng **15 dòng stdout**.

## 13. Kết luận

Với collector bản đồ, hãy suy luận theo thứ tự **`Stream<T>` → `keyMapper: T→K` → `valueMapper: T→U` → `Collector<T,?,Map<K,U>>` → `Map<K,U>`**. `var` chỉ giúp viết gọn tên biến cục bộ sau khi compiler đã biết kiểu của biểu thức; nó không tự thay đổi hợp đồng generic. Khi keys có thể trùng, phải quyết định merge policy; khi dữ liệu phải sửa sau thu thập, chọn collector/map factory khác. Đây là cơ chế quan trọng của Java 10 vẫn được áp dụng trên các JDK hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 25 — `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): chữ ký `toUnmodifiableMap`, `toMap`, `groupingBy`, duplicate keys, null và mutability.
- [Oracle Java SE 25 — `Collector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html): vai trò `T` (input), `A` (accumulator) và `R` (result).
- [Oracle Java SE 25 — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `map`, `filter`, `collect` và generic type của Stream.
- [Oracle Java SE 25 — `Function`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html): `Function<? super T, ? extends R>` và `Function.identity()`.
- [Java Language Specification `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): target typing, chọn overload và generic method invocation.
- [Java Language Specification `18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html): nền tảng ràng buộc suy luận kiểu generic.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): `var`, kiểu tĩnh và phạm vi suy luận của initializer.