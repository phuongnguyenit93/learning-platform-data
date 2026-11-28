# Array component và bẫy equality theo tham chiếu

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record tự sinh `equals(Object)` và `hashCode()` dựa trên các record component. Với component kiểu tham chiếu, ngữ nghĩa mặc định tương đương `Objects.equals` và `Objects.hashCode`. Điều này hoạt động đúng với các kiểu như `String` hoặc record lồng nhau, nhưng có một bẫy quan trọng: **mảng không ghi đè `equals` và `hashCode` của `Object`**. Vì vậy record chứa mảng mặc định so sánh component theo identity của mảng, không theo nội dung các phần tử.

Nếu nghiệp vụ muốn hai mảng có cùng nội dung được xem là cùng một giá trị, cần chọn rõ ngữ nghĩa so sánh, mã băm tương ứng và cách bảo vệ mảng khỏi thay đổi ngoài ý muốn.

## 1. Vì sao hai record chứa mảng giống nội dung vẫn không bằng nhau?

Xét ví dụ:

```java
record Packet(byte[] data) {}

byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

Packet a = new Packet(first);
Packet b = new Packet(second);
Packet c = new Packet(first);

System.out.println(java.util.Arrays.equals(first, second)); // true
System.out.println(a.equals(b)); // false
System.out.println(a.equals(c)); // true
```

`first` và `second` là hai mảng riêng biệt. Chúng chứa cùng các byte nhưng `first.equals(second)` vẫn là `false` vì mảng kế thừa `Object.equals`, vốn so sánh identity. Record mặc định dùng ngữ nghĩa `equals` của component nên `a` và `b` cũng không bằng nhau.

`c` chứa chính tham chiếu mảng `first`, nên component của `a` và `c` là cùng một mảng. Vì vậy `a.equals(c)` trả về `true`.

Có thể phân biệt ba phép so sánh:

| Biểu thức | Ý nghĩa | Kết quả trong ví dụ |
| --- | --- | --- |
| `first == second` | Hai biến có cùng tham chiếu mảng không? | `false` |
| `Arrays.equals(first, second)` | Các phần tử tương ứng có bằng nhau không? | `true` |
| `a.equals(b)` | Các component của hai record có bằng nhau theo ngữ nghĩa mặc định không? | `false` |

Đây không phải lỗi của record. Record giữ nguyên hợp đồng `equals` của kiểu component; với mảng, hợp đồng mặc định là so sánh theo identity.

## 2. Quy tắc này vẫn đúng nếu khai báo component là `Object`

Việc khai báo component là `Object` thay vì `byte[]` không tự làm phép so sánh trở thành so sánh nội dung:

```java
record Payload(Object value) {}

Payload a = new Payload(new int[] {1, 2});
Payload b = new Payload(new int[] {1, 2});

System.out.println(a.equals(b)); // false
```

Component `value` là tham chiếu đến một mảng. Khi so sánh hai component, `Objects.equals(a.value(), b.value())` gọi `equals` của mảng ở vế trái; mảng vẫn dùng so sánh identity. Kiểu khai báo rộng hơn không thay đổi cách mảng triển khai `equals`.

## 3. Chọn đúng API của `Arrays`

Lớp `java.util.Arrays` cung cấp các phương thức so sánh và mã băm theo nội dung mảng. Chọn phương thức phù hợp với loại mảng và cấu trúc dữ liệu:

| API | Mục đích | Cách xử lý |
| --- | --- | --- |
| `Arrays.equals(primitiveArray1, primitiveArray2)` | So sánh mảng primitive một chiều | So sánh từng phần tử theo kiểu primitive. |
| `Arrays.equals(objectArray1, objectArray2)` | So sánh mảng tham chiếu một chiều | So sánh từng phần tử bằng ngữ nghĩa `Objects.equals`. |
| `Arrays.deepEquals(objectArray1, objectArray2)` | So sánh sâu mảng tham chiếu, kể cả mảng lồng nhau | Đệ quy vào các phần tử là mảng. |
| `Arrays.hashCode(array)` | Mã băm theo nội dung mảng một chiều | Tương ứng với ngữ nghĩa `Arrays.equals`. |
| `Arrays.deepHashCode(objectArray)` | Mã băm sâu cho mảng tham chiếu lồng nhau | Tương ứng với ngữ nghĩa `Arrays.deepEquals`. |

Ví dụ với mảng primitive:

```java
import java.util.Arrays;

int[] left = {10, 20, 30};
int[] right = {10, 20, 30};

System.out.println(left.equals(right));         // false
System.out.println(Arrays.equals(left, right)); // true
System.out.println(Arrays.hashCode(left) == Arrays.hashCode(right)); // true
```

Với mảng object một chiều:

```java
import java.util.Arrays;

String[] left = {"Java", "Records"};
String[] right = {"Java", "Records"};

System.out.println(Arrays.equals(left, right)); // true
```

Ở đây `Arrays.equals` so sánh từng cặp `String` bằng `String.equals`, nên không yêu cầu các chuỗi phải là cùng instance.

### Mảng lồng nhau cần phép so sánh sâu

Mảng hai chiều trong Java thực chất là mảng chứa các mảng khác. `Arrays.equals` trên mảng ngoài chỉ so sánh các hàng bằng `equals` của từng hàng; mỗi hàng vẫn là mảng và so sánh theo identity:

```java
import java.util.Arrays;

int[][] left = {{1, 2}, {3, 4}};
int[][] right = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(left, right));     // false
System.out.println(Arrays.deepEquals(left, right)); // true
```

Với `int[][]`, kiểu mảng ngoài là `int[][]` và cũng có thể truyền vào API nhận `Object[]` vì mỗi phần tử của nó là một `int[]`. `deepEquals` đi vào từng hàng và dùng phép so sánh phù hợp với kiểu mảng con.

Quy tắc tương tự áp dụng cho mã băm:

```java
System.out.println(Arrays.hashCode(left) == Arrays.hashCode(right)); // không được bảo đảm
System.out.println(Arrays.deepHashCode(left)
        == Arrays.deepHashCode(right)); // true
```

Khi dùng `deepEquals`, hãy dùng `deepHashCode` tương ứng. Không ghép `deepEquals` với `hashCode` nông vì như vậy có thể phá vỡ hợp đồng `equals`/`hashCode`.

## 4. Nếu muốn record so sánh mảng theo nội dung

Khi mảng đại diện cho một giá trị, có thể ghi đè cả `equals` và `hashCode` trong record. Ví dụ sau mô hình hóa một chuỗi byte:

```java
import java.util.Arrays;
import java.util.Objects;

record ByteValue(byte[] bytes) {
    ByteValue {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof ByteValue that
                && Arrays.equals(this.bytes, that.bytes));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Implementation trên có bốn điểm quan trọng:

1. Compact constructor dùng `clone()` để sao chép mảng đầu vào. Thay đổi mảng gốc sau khi tạo record không làm thay đổi dữ liệu nội bộ.
2. Accessor `bytes()` trả về bản sao, không để bên gọi sửa trực tiếp mảng bên trong.
3. `equals` dùng `Arrays.equals` để so sánh nội dung.
4. `hashCode` dùng `Arrays.hashCode` để cùng nội dung có cùng mã băm.

Ví dụ sử dụng:

```java
ByteValue first = new ByteValue(new byte[] {1, 2, 3});
ByteValue second = new ByteValue(new byte[] {1, 2, 3});

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Hai record vẫn là hai instance riêng biệt; chỉ có ngữ nghĩa `equals` được định nghĩa theo nội dung byte. Đây là ví dụ về record có value equality theo miền nghiệp vụ.

### Vì sao cần sao chép cả ở constructor và accessor?

Nếu chỉ sao chép trong constructor nhưng dùng accessor mặc định, bên gọi vẫn nhận được tham chiếu đến mảng nội bộ:

```java
record UnsafeBytes(byte[] data) {
    UnsafeBytes {
        data = data.clone();
    }
}

UnsafeBytes value = new UnsafeBytes(new byte[] {1, 2});
value.data()[0] = 99; // Có thể sửa mảng nội bộ qua accessor mặc định.
```

Ngược lại, nếu chỉ ghi đè accessor nhưng không sao chép đầu vào trong constructor, bên gọi vẫn có thể sửa mảng gốc sau khi truyền vào. Để bảo vệ một mảng một chiều, thường cần cả hai chiều sao chép.

## 5. Mảng lồng nhau: sao chép nông chưa đủ

`clone()` của mảng hai chiều chỉ tạo mảng ngoài mới; các hàng bên trong vẫn là những mảng cũ. Nếu yêu cầu dữ liệu bất biến theo nội dung, cần sao chép cả từng hàng và trả bản sao sâu qua accessor.

Ví dụ cho ma trận `int[][]`:

```java
import java.util.Arrays;
import java.util.Objects;

record IntMatrix(int[][] values) {
    IntMatrix {
        Objects.requireNonNull(values, "values");
        values = Arrays.stream(values)
            .map(row -> Objects.requireNonNull(row, "row").clone())
            .toArray(int[][]::new);
    }

    @Override
    public int[][] values() {
        return Arrays.stream(values)
            .map(row -> row.clone())
            .toArray(int[][]::new);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof IntMatrix that
                && Arrays.deepEquals(this.values, that.values));
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(values);
    }
}
```

Ở đây constructor sao chép mảng ngoài và từng hàng; accessor cũng trả bản sao của mảng ngoài cùng các hàng. `deepEquals` và `deepHashCode` đảm bảo hai ma trận có cùng cấu trúc và giá trị được xem là bằng nhau.

Ví dụ này giả định ma trận và từng hàng không `null`. Nếu mô hình dữ liệu cho phép hàng `null`, cần định nghĩa chính sách sao chép và so sánh phù hợp thay vì gọi `clone()` trực tiếp trên hàng.

## 6. Khi nào giữ equality theo identity của mảng là hợp lý?

Không phải mọi record chứa mảng đều cần so sánh theo nội dung. Nếu component mảng được dùng như một tham chiếu đến vùng dữ liệu hoặc một buffer cụ thể, việc giữ ngữ nghĩa identity mặc định có thể đúng với mục đích thiết kế.

Ví dụ:

```java
record BufferHandle(byte[] storage) {}

byte[] storage = new byte[1024];
BufferHandle first = new BufferHandle(storage);
BufferHandle second = new BufferHandle(storage);

System.out.println(first.equals(second)); // true: cùng tham chiếu storage
```

Trong trường hợp này, hai record cùng tham chiếu đến một vùng lưu trữ. Nếu tạo một mảng mới cùng kích thước và nội dung, record mới không nhất thiết đại diện cho cùng buffer. Hãy chọn identity semantics khi danh tính của vùng dữ liệu mới là điều nghiệp vụ cần phân biệt.

Ngược lại, với byte sequence, checksum input, nội dung file hoặc vector số, thường mong muốn equality theo nội dung. Khi đó nên đóng gói mảng bằng một value type có `equals`/`hashCode` rõ ràng như `ByteValue` ở trên.

## 7. Ảnh hưởng khi dùng record chứa mảng làm khóa collection

Với record mặc định:

```java
import java.util.HashSet;
import java.util.Set;

record ArrayKey(int[] values) {}

Set<ArrayKey> keys = new HashSet<>();
keys.add(new ArrayKey(new int[] {1, 2}));
keys.add(new ArrayKey(new int[] {1, 2}));

System.out.println(keys.size()); // 2
```

Hai mảng khác tham chiếu, nên hai record mặc định không bằng nhau. `HashSet` có thể giữ cả hai phần tử.

Nếu record tùy chỉnh `equals`/`hashCode` theo nội dung mảng, hai mảng cùng phần tử sẽ được xem là cùng khóa. Tuy nhiên, nếu mảng nội bộ vẫn có thể bị thay đổi, `hashCode` theo nội dung có thể đổi sau khi phần tử đã được thêm vào `HashSet` hoặc dùng làm khóa `HashMap`. Khi đó tra cứu hoặc xóa có thể không hoạt động như mong đợi.

Vì vậy, khi chọn content equality cho mảng:

- Sao chép dữ liệu đầu vào trong constructor.
- Không trả trực tiếp mảng nội bộ qua accessor.
- Với mảng lồng nhau, sao chép sâu theo cấu trúc cần bảo vệ.
- Dùng cặp phương thức tương ứng: `Arrays.equals`/`Arrays.hashCode` hoặc `Arrays.deepEquals`/`Arrays.deepHashCode`.

Lưu ý thêm: với record mặc định, nội dung mảng thay đổi không làm thay đổi phép so sánh hoặc mã băm của component, vì mảng dùng identity-based `equals`/`hashCode`. Với record tùy chỉnh so sánh sâu, nội dung thay đổi có thể làm đổi `equals` và `hashCode`; vì thế bảo vệ mảng là đặc biệt quan trọng.

## 8. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Hai record chứa hai mảng cùng phần tử mặc định bằng nhau. | **Sai** | Mảng dùng `Object.equals` nên so sánh identity. |
| `Arrays.equals` so sánh nội dung mảng primitive. | **Đúng** | Có overload dành cho từng kiểu mảng primitive. |
| `Arrays.equals` trên `int[][]` luôn so sánh sâu từng số nguyên. | **Sai** | Nó so sánh các hàng bằng equality của mảng con; dùng `deepEquals`. |
| `Arrays.deepEquals` phù hợp cho mảng lồng nhau. | **Đúng** | Phương thức đi sâu vào phần tử là mảng. |
| Ghi đè `equals` mà không ghi đè `hashCode` vẫn an toàn cho hash collection. | **Sai** | Phải giữ hợp đồng: bằng nhau thì cùng mã băm. |
| Chỉ clone mảng trong constructor là đủ để bảo vệ record khỏi thay đổi bên ngoài. | **Sai** | Accessor mặc định vẫn có thể trả mảng nội bộ. |
| Mảng cùng tham chiếu có thể khiến hai record mặc định bằng nhau. | **Đúng** | Component tham chiếu là cùng một mảng. |

## 9. Checklist khi thiết kế record có array component

1. Mảng đang đại diện cho một vùng dữ liệu cụ thể hay một giá trị được xác định bởi nội dung?
2. Ngữ nghĩa mặc định theo identity có đúng với yêu cầu không?
3. Nếu cần so sánh nội dung, nên dùng `Arrays.equals` hay `Arrays.deepEquals`?
4. `hashCode` đã dùng đúng phương thức tương ứng chưa?
5. Constructor có sao chép dữ liệu đầu vào không?
6. Accessor có trả bản sao thay vì mảng nội bộ không?
7. Với mảng lồng nhau, đã bảo vệ các mảng con chưa?
8. Record có được dùng làm khóa `HashMap`/phần tử `HashSet` trong khi dữ liệu có thể thay đổi không?

**Ghi nhớ:** Record mặc định so sánh array component theo identity vì mảng kế thừa `Object.equals` và `Object.hashCode`. Nếu muốn equality theo nội dung, hãy tự triển khai cặp `equals`/`hashCode` bằng `Arrays.equals`/`Arrays.hashCode` hoặc các phiên bản deep tương ứng, đồng thời sao chép phòng vệ để bảo vệ trạng thái của mảng.

## Tài liệu chính thức

- [Java SE 26 API — `java.util.Arrays.equals`, `deepEquals`, `hashCode` và `deepHashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html).
- [Java SE 26 API — `java.lang.Object.equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html).
- [Java SE 26 API — `java.lang.Record`, hợp đồng equality và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
