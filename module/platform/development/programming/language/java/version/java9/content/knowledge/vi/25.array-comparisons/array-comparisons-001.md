# So sánh từ điển bằng Arrays.compare

Từ Java 9, lớp `java.util.Arrays` cung cấp `Arrays.compare(...)` để so sánh hai mảng theo thứ tự từ điển (lexicographical order). Phương thức xem mỗi mảng như một dãy phần tử có thứ tự: so sánh từ đầu đến cuối, dừng ở vị trí khác nhau đầu tiên, hoặc dùng độ dài để quyết định khi một mảng là tiền tố của mảng còn lại.

`Arrays.compare` hữu ích khi cần sắp xếp hoặc so sánh các dãy giá trị, khóa ghép, phiên bản dạng mảng hay dữ liệu nhị phân đã được biểu diễn thành các phần tử. Phương thức không sắp xếp và không thay đổi hai mảng; nó chỉ trả về kết quả so sánh.

## 1. Quy tắc so sánh từ điển

Với hai mảng `a` và `b` có cùng kiểu phần tử, quy tắc được áp dụng theo thứ tự:

1. So sánh `a[0]` với `b[0]`.
2. Nếu hai phần tử bằng nhau theo quy tắc so sánh của kiểu dữ liệu, chuyển sang vị trí tiếp theo.
3. Tại vị trí đầu tiên có khác biệt, kết quả so sánh của hai phần tử quyết định thứ tự của cả hai mảng.
4. Nếu tất cả phần tử trong phần chung đều bằng nhau, mảng ngắn hơn đứng trước mảng dài hơn.
5. Nếu hai mảng có cùng độ dài và mọi cặp phần tử đều bằng nhau theo quy tắc so sánh, kết quả là 0.

Ví dụ:

```java
int[] a = {2, 4, 7};
int[] b = {2, 5, 1};

int result = Arrays.compare(a, b);
```

Hai mảng có phần tử đầu tiên cùng là 2. Ở vị trí tiếp theo, 4 nhỏ hơn 5 nên `a` đứng trước `b`. Phần tử 7 và 1 không còn ảnh hưởng vì thứ tự đã được xác định tại vị trí khác nhau đầu tiên.

Một số trường hợp biên:

| Mảng thứ nhất | Mảng thứ hai | Kết quả |
|---|---|---|
| `[1, 3, 5]` | `[1, 4, 0]` | Mảng thứ nhất nhỏ hơn vì 3 nhỏ hơn 4 |
| `[2, 4]` | `[2, 4, 0]` | Mảng thứ nhất nhỏ hơn vì là tiền tố ngắn hơn |
| `[2, 4, 0]` | `[2, 4]` | Mảng thứ nhất lớn hơn vì dài hơn sau phần chung bằng nhau |
| `[7, 8]` | `[7, 8]` | Bằng nhau, kết quả 0 |
| `[]` | `[1]` | Mảng rỗng nhỏ hơn mảng có một phần tử |
| `[]` | `[]` | Bằng nhau, kết quả 0 |

Đây là so sánh theo thứ tự phần tử, không phải so sánh độ dài trước. Một mảng dài hơn vẫn có thể đứng trước mảng ngắn hơn nếu phần tử khác nhau đầu tiên của nó nhỏ hơn.

## 2. Giá trị trả về

`Arrays.compare` trả về một số nguyên:

- Số âm: mảng thứ nhất nhỏ hơn mảng thứ hai.
- 0: hai mảng bằng nhau theo quy tắc so sánh đang dùng.
- Số dương: mảng thứ nhất lớn hơn mảng thứ hai.

Chỉ dựa vào dấu của kết quả. Không giả định phương thức luôn trả về chính xác `-1` hoặc `1`. Cách viết rõ ràng thường là:

```java
int result = Arrays.compare(first, second);

if (result < 0) {
    System.out.println("first đứng trước second");
} else if (result > 0) {
    System.out.println("first đứng sau second");
} else {
    System.out.println("Hai mảng bằng nhau theo thứ tự so sánh");
}
```

`Arrays.compare(a, b) == 0` cũng không nhất thiết tương đương với `Arrays.equals(a, b)` trong mọi trường hợp. Với mảng object, comparator có thể xem hai object khác nhau là bằng nhau về thứ tự nếu comparator trả về 0. `Arrays.equals` kiểm tra tính bằng nhau theo `equals` của phần tử; `Arrays.compare` kiểm tra thứ tự.

## 3. Các overload thường dùng

`Arrays.compare` có overload cho các mảng primitive và mảng object:

| Kiểu mảng | Cách gọi |
|---|---|
| Primitive | `Arrays.compare(int[] a, int[] b)` |
| Primitive khác | `Arrays.compare(byte[] a, byte[] b)`, `Arrays.compare(long[] a, long[] b)`, `Arrays.compare(double[] a, double[] b)` và các kiểu primitive còn lại |
| Object có thứ tự tự nhiên | `Arrays.compare(T[] a, T[] b)` với `T` triển khai `Comparable` |
| Object dùng quy tắc riêng | `Arrays.compare(T[] a, T[] b, Comparator<? super T> cmp)` |
| Một đoạn của hai mảng | Overload nhận chỉ số bắt đầu và kết thúc của từng mảng |

Các overload so sánh đoạn mảng dùng khoảng nửa mở `[fromIndex, toIndex)`: lấy phần tử từ chỉ số bắt đầu và không lấy chỉ số kết thúc. Ví dụ:

```java
int[] full = {99, 2, 4, 99};
int[] pair = {2, 4};

int result = Arrays.compare(full, 1, 3, pair, 0, 2);
// So sánh [2, 4] với [2, 4], kết quả là 0.
```

Chỉ số và khoảng phải hợp lệ đối với mảng tương ứng. Hãy kiểm tra ranh giới khi tính chỉ số động từ dữ liệu bên ngoài.

## 4. So sánh mảng object và dùng Comparator

Với mảng object, overload không nhận comparator sử dụng thứ tự tự nhiên của phần tử. Kiểu phần tử cần triển khai `Comparable`:

```java
String[] first = {"An", "Binh"};
String[] second = {"An", "Chi"};

int result = Arrays.compare(first, second);
```

`String` triển khai `Comparable<String>`, vì vậy Java có thể so sánh các phần tử theo thứ tự tự nhiên của chuỗi.

Nếu cần quy tắc khác, truyền `Comparator`:

```java
String[] lower = {"An", "binh"};
String[] upper = {"An", "Binh"};

int natural = Arrays.compare(lower, upper);
int ignoreCase = Arrays.compare(
        lower,
        upper,
        String.CASE_INSENSITIVE_ORDER
);
```

Trong thứ tự tự nhiên, chữ thường và chữ hoa có vị trí khác nhau theo thứ tự ký tự của `String`. Comparator không phân biệt hoa thường có thể xem hai phần tử tương ứng là bằng nhau.

Comparator nên xác định một thứ tự nhất quán và có tính bắc cầu. Nếu comparator trả về 0 cho hai object khác nhau, `Arrays.compare` coi chúng bằng nhau về thứ tự tại vị trí đó; điều này không khẳng định hai object có cùng tham chiếu hoặc `equals` trả về true.

Với mảng object có phần tử `null`, cách xử lý phụ thuộc overload và comparator. So sánh tự nhiên không tự định nghĩa thứ tự cho `null`; nếu dữ liệu có thể chứa null, hãy dùng comparator có quy tắc null rõ ràng, chẳng hạn `Comparator.nullsFirst(...)` hoặc `Comparator.nullsLast(...)`. Bản thân hai tham chiếu mảng truyền vào cũng phải khác null.

## 5. Phân biệt so sánh signed và unsigned

Với các kiểu số nguyên có dấu như `byte`, `short`, `int` và `long`, `Arrays.compare` dùng thứ tự số có dấu. Java diễn giải bit cao nhất là bit dấu.

Khi cần so sánh các giá trị theo cách diễn giải không dấu, Java 9 cũng cung cấp `Arrays.compareUnsigned` cho mảng `byte[]`, `short[]`, `int[]` và `long[]`.

Ví dụ với byte:

```java
byte[] highBit = {(byte) 0xFF};
byte[] lowValue = {(byte) 0x01};

System.out.println(Arrays.compare(highBit, lowValue) < 0);
System.out.println(Arrays.compareUnsigned(highBit, lowValue) > 0);
```

Kết quả:

```text
true
true
```

Giải thích:

- `(byte) 0xFF` có giá trị signed là -1. Theo thứ tự có dấu, -1 nhỏ hơn 1.
- Khi so sánh unsigned, cùng bit pattern `0xFF` được diễn giải là 255. Vì vậy 255 lớn hơn 1.
- `compareUnsigned` không sửa bit hoặc chuyển đổi mảng nguồn. Nó chỉ thay đổi cách diễn giải giá trị khi so sánh.

Dùng so sánh unsigned khi các phần tử biểu diễn trường nhị phân, byte dữ liệu, số nguyên không dấu trong giao thức hoặc định dạng lưu trữ. Với dữ liệu số học thông thường của Java, `Arrays.compare` theo thứ tự có dấu thường là lựa chọn phù hợp.

## 6. Lưu ý với float và double

Khi so sánh `float[]` hoặc `double[]`, thứ tự phần tử tuân theo quy tắc của `Float.compare` hoặc `Double.compare`:

- `NaN` được xếp sau các giá trị số thông thường, kể cả vô cực dương.
- Các giá trị NaN được xem là bằng nhau theo phép so sánh này.
- `-0.0` nhỏ hơn `+0.0`.

Điểm cuối khác với phép so sánh toán học `-0.0 == +0.0` trong Java, vốn cho kết quả true. Nếu thứ tự của dữ liệu dấu phẩy động quan trọng, hãy nhớ rằng `Arrays.compare` dùng quy tắc so sánh tổng thứ tự của wrapper tương ứng, không chỉ dùng toán tử `<` và `>`.

## 7. Ví dụ Java chạy được

Ví dụ sau minh họa thứ tự từ điển, tiền tố, mảng bằng nhau, signed/unsigned, comparator và signed zero.

```java
import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        int[] first = {2, 4, 7};
        int[] second = {2, 5, 1};

        System.out.println("first < second: "
                + (Arrays.compare(first, second) < 0));

        System.out.println("shorter prefix < longer: "
                + (Arrays.compare(new int[]{2, 4}, new int[]{2, 4, 0}) < 0));

        System.out.println("equal contents: "
                + (Arrays.compare(new int[]{2, 4}, new int[]{2, 4}) == 0));

        byte[] highBit = {(byte) 0xFF};
        byte[] lowValue = {(byte) 0x01};

        System.out.println("signed byte order: "
                + (Arrays.compare(highBit, lowValue) < 0));
        System.out.println("unsigned byte order: "
                + (Arrays.compareUnsigned(highBit, lowValue) > 0));

        String[] lower = {"An", "binh"};
        String[] upper = {"An", "Binh"};

        System.out.println("natural String order: "
                + (Arrays.compare(lower, upper) > 0));
        System.out.println("case-insensitive order equal: "
                + (Arrays.compare(lower, upper, String.CASE_INSENSITIVE_ORDER) == 0));

        double[] floatingA = {-0.0, Double.NaN};
        double[] floatingB = {+0.0, Double.NaN};

        System.out.println("negative zero < positive zero: "
                + (Arrays.compare(floatingA, floatingB) < 0));
    }
}
```

Lưu mã vào `Main.java` và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
first < second: true
shorter prefix < longer: true
equal contents: true
signed byte order: true
unsigned byte order: true
natural String order: true
case-insensitive order equal: true
negative zero < positive zero: true
```

Từng kết quả phản ánh một quy tắc riêng:

1. Mảng `first` nhỏ hơn `second` vì 4 nhỏ hơn 5 tại vị trí khác nhau đầu tiên.
2. Mảng `[2, 4]` nhỏ hơn `[2, 4, 0]` vì nó là tiền tố ngắn hơn.
3. Hai mảng có cùng phần tử theo cùng thứ tự cho kết quả 0.
4. Byte `0xFF` nhỏ hơn `0x01` theo signed order nhưng lớn hơn theo unsigned order.
5. Thứ tự tự nhiên của chuỗi phân biệt chữ hoa và chữ thường; comparator case-insensitive cho kết quả 0.
6. `-0.0` được xếp trước `+0.0` trong thứ tự của `Double.compare`.

## 8. Arrays.compare khác gì equals và sort?

| API | Mục đích | Có thay đổi mảng nguồn không? |
|---|---|---|
| `Arrays.compare(a, b)` | Xác định thứ tự từ điển giữa hai mảng | Không |
| `Arrays.compareUnsigned(a, b)` | So sánh theo thứ tự không dấu cho các kiểu được hỗ trợ | Không |
| `Arrays.equals(a, b)` | Kiểm tra hai mảng có cùng độ dài và phần tử tương ứng bằng nhau | Không |
| `Arrays.sort(a)` | Sắp xếp phần tử trong một mảng | Có |

`Arrays.equals` trả về boolean và phù hợp khi chỉ cần kiểm tra bằng nhau. `Arrays.compare` trả về dấu thứ tự, nên phù hợp khi cần sắp xếp nhiều mảng hoặc quyết định mảng nào đứng trước.

`Arrays.sort` sắp xếp một mảng tại chỗ. Nó không thay thế `Arrays.compare`: nếu chỉ muốn so sánh hai dãy theo thứ tự hiện tại, không nên sắp xếp chúng trước vì việc đó làm thay đổi ý nghĩa vị trí phần tử.

## 9. Ứng dụng thực tế

**Sắp xếp các dãy số**

Có thể dùng `Arrays.compare` làm comparator khi sắp xếp một danh sách các mảng:

```java
List<int[]> sequences = new ArrayList<>();
sequences.add(new int[]{2, 4});
sequences.add(new int[]{1, 9});
sequences.add(new int[]{2, 3, 8});

sequences.sort(Arrays::compare);
```

Các dãy được sắp theo thứ tự từ điển. Đoạn mã này cần import `java.util.ArrayList` và `java.util.List`.

**So sánh khóa ghép**

Một khóa gồm nhiều trường có thể được biểu diễn thành mảng hoặc object có comparator. So sánh từ điển giúp trường đầu tiên có khác biệt quyết định thứ tự; các trường sau chỉ dùng khi trường trước bằng nhau. Trong ứng dụng nghiệp vụ, hãy chọn kiểu dữ liệu thể hiện đúng miền giá trị và tránh ép các trường không cùng kiểu vào một mảng chỉ để tận dụng API.

**So sánh dữ liệu nhị phân**

`Arrays.compareUnsigned` phù hợp khi mỗi phần tử là một đơn vị bit pattern cần được hiểu như giá trị không dấu. Điều này hữu ích khi so sánh các đoạn byte hoặc số nguyên được giải mã từ giao thức. Cần xác định trước thứ tự byte (endianness) khi chuyển nhiều byte thành số nguyên; `compareUnsigned` không tự giải mã byte order cho bạn.

## 10. Lỗi thường gặp

- **Chỉ so sánh độ dài:** thứ tự từ điển so sánh phần tử trước, chỉ xét độ dài khi phần chung bằng nhau.
- **Giả định kết quả chỉ là -1, 0 hoặc 1:** chỉ dựa vào âm, bằng 0 hoặc dương.
- **Dùng compare khi chỉ cần kiểm tra bằng nhau:** `Arrays.equals` diễn đạt mục tiêu rõ hơn.
- **Nhầm signed với unsigned:** `byte` trong Java có dấu; dùng `compareUnsigned` nếu bit pattern phải được hiểu là giá trị không dấu.
- **Quên comparator cho object:** mảng object cần thứ tự tự nhiên hoặc comparator; comparator phải phù hợp với dữ liệu và null policy.
- **So sánh hai kiểu mảng khác nhau trực tiếp:** không có overload chung cho mọi cặp kiểu primitive; chuyển đổi dữ liệu hoặc viết comparator có chủ đích.
- **Cho rằng phương thức sắp xếp mảng:** `Arrays.compare` không thay đổi thứ tự ban đầu của hai mảng.
- **Bỏ qua NaN và signed zero:** thứ tự float/double tuân theo `Float.compare` và `Double.compare`.

## 11. Checklist khi sử dụng

- Hai mảng có cùng kiểu phần tử hay cần chuyển đổi trước?
- Cần thứ tự có dấu hay không dấu?
- Với object, thứ tự tự nhiên có đúng nghiệp vụ hay cần Comparator?
- Có phần tử null hoặc comparator cần quy tắc xử lý null không?
- Có đang so sánh toàn mảng hay chỉ một đoạn `[fromIndex, toIndex)`?
- Mã có chỉ kiểm tra dấu của kết quả thay vì dựa vào giá trị nguyên cụ thể không?
- Dữ liệu float/double có thể chứa NaN hoặc cả hai dạng số 0 không?

`Arrays.compare` là API hiện hành từ Java 9 để so sánh hai mảng theo thứ tự từ điển. Nắm rõ quy tắc phần tử khác nhau đầu tiên, trường hợp tiền tố, thứ tự signed/unsigned và comparator cho object giúp lựa chọn đúng overload và tránh nhầm lẫn giữa so sánh, kiểm tra bằng nhau và sắp xếp.
