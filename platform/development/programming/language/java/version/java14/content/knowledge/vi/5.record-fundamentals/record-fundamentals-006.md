# Record: các phương thức `equals`, `hashCode` và `toString` được tạo

## 1. Mục tiêu và bối cảnh

Một record dùng để mô tả **một nhóm dữ liệu có tên**, trong đó những thành phần (record components) được khai báo ngay ở phần tiêu đề:

```java
record Product(String code, int quantity) {}
```

Chỉ với khai báo này, trình biên dịch cung cấp constructor chính, các trường thành phần `private final`, các phương thức đọc `code()` và `quantity()`, cùng ba phương thức quan trọng:

- `equals(Object)`: kiểm tra hai đối tượng record thuộc **cùng lớp** và có **tất cả thành phần tương ứng bằng nhau**.
- `hashCode()`: tính một mã băm từ các thành phần và duy trì hợp đồng “bằng nhau thì cùng mã băm”.
- `toString()`: tạo chuỗi thể hiện tên record, tên và giá trị các thành phần để con người dễ đọc.

Điểm khác biệt so với một lớp thông thường không ghi đè `equals` là: `Object.equals` mặc định kiểm tra **cùng tham chiếu**, còn `equals` do record tạo ra kiểm tra **giá trị của dữ liệu cấu thành**. Hai đối tượng `new Product("A01", 3)` độc lập có thể bằng nhau.

Record được giới thiệu ở Java 14 dưới dạng tính năng thử nghiệm và trở thành tính năng **chuẩn từ Java 16**. Bài học tập trung vào ngữ nghĩa **vẫn áp dụng trong Java 17+**, không cần công tắc preview hay cơ chế đã lỗi thời.

## 2. Phạm vi các phương thức do trình biên dịch cung cấp

Xét `record Point(int x, int y) {}`. Một mô hình để hiểu cấu trúc là lớp có hai trường số nguyên bất biến, constructor nhận `x, y`, hai accessor và ba phương thức lấy dữ liệu làm cơ sở so sánh/hiển thị. **Không hiểu mô hình này là nguồn Java mà trình biên dịch nhất thiết tạo ra**: mã máy và thuật toán cụ thể do trình biên dịch/JDK quyết định.

| Phương thức | Chữ ký sử dụng | Dữ liệu mà bản mặc định dựa vào |
| --- | --- | --- |
| `equals` | `public boolean equals(Object obj)` | Kiểu record và **tất cả trường thành phần** |
| `hashCode` | `public int hashCode()` | **Tất cả trường thành phần** |
| `toString` | `public String toString()` | Tên record, tên và biểu diễn của **tất cả trường thành phần** |

Record có thể tự khai báo một hoặc nhiều phương thức trên; khi đó trình biên dịch không tạo bản mặc định cho phương thức đã khai báo tường minh. Những thành viên `static` và các phương thức bổ trợ khác **không trở thành thành phần** và không trực tiếp tham gia thuật toán mặc định.

Mặc dù record cung cấp các accessor như `x()` và `y()`, **các phương thức được tạo đọc giá trị trường thành phần trực tiếp** để so sánh, băm và trình bày. Chúng không cần gọi accessor tự viết lại. Điều này quan trọng nếu một accessor bị tùy biến để trả giá trị đã biến đổi.

## 3. `equals(Object)`: so sánh đúng lớp và đúng giá trị thành phần

### 3.1. Điều kiện tổng quát

Với hai đối tượng `a` và `b`, bản `equals` được tạo trả `true` khi:

1. `b` thuộc **chính lớp record** của `a` (không chỉ cùng hình dạng dữ liệu).
2. Mỗi thành phần tương ứng có giá trị bằng nhau theo quy tắc của **kiểu thành phần**.

Ví dụ:

```java
record Point(int x, int y) {}
record Position(int x, int y) {}

Point p1 = new Point(1, 2);
Point p2 = new Point(1, 2);
Point p3 = new Point(1, 3);

boolean a = p1 == p2;                  // false: khác tham chiếu
boolean b = p1.equals(p2);             // true: cùng giá trị
boolean c = p1.equals(p3);             // false: y khác nhau
boolean d = p1.equals(new Position(1, 2)); // false: khác lớp record
boolean e = p1.equals(null);           // false
```

Record ngầm định là `final`, nên không có lớp con nào bổ sung thành phần làm thay đổi phép so sánh mặc định. Nếu một record **không có thành phần**, mọi đối tượng thuộc cùng lớp record rỗng đó đều bằng nhau theo bản `equals` tự tạo.

### 3.2. Kiểu nguyên thủy, tham chiếu và số thực

| Kiểu thành phần | Cách xét bằng nhau | Lưu ý |
| --- | --- | --- |
| `int`, `long`, `boolean`, `char`, các nguyên thủy khác | Tương đương so sánh bằng phương thức `compare` của lớp bao nguyên thủy tương ứng | Cùng giá trị thì bằng nhau |
| `float`, `double` | Theo `Float.compare` hoặc `Double.compare` | Hai giá trị `NaN` bằng nhau; `+0.0` và `-0.0` không bằng nhau |
| `String`, `List`, một record khác hoặc tham chiếu nói chung | Tương đương `Objects.equals(a, b)` | Hai `null` bằng nhau; còn lại dựa vào `equals` của kiểu tham chiếu |
| Mảng `int[]`, `String[]`, … | Dùng `equals` mặc định của mảng, tức so **cùng tham chiếu mảng** | Hai mảng khác nhau chứa phần tử giống nhau vẫn không bằng nhau |

Ví dụ với số thực:

```java
record Measurement(double value) {}

boolean sameNaN = new Measurement(Double.NaN)
        .equals(new Measurement(Double.NaN)); // true
boolean sameZeros = new Measurement(+0.0)
        .equals(new Measurement(-0.0));       // false
```

Đừng thay quy tắc số thực bằng cách tự viết `a.value() == b.value()`: với `NaN` và số không có dấu, toán tử `==` cho kết quả khác `equals` mặc định của record.

Với `record Customer(String name) {}`, hai đối tượng chứa `null` ở `name` vẫn có thể bằng nhau. Constructor không tự từ chối `null`, nên muốn ràng buộc tên hợp lệ thì cần kiểm tra đầu vào. Với `String`, `equals` so **nội dung ký tự**, không bắt buộc hai trường trỏ cùng đối tượng `String`.

**Mảng là trường hợp dễ nhầm nhất.** Record không tự dùng `Arrays.equals` hay `Arrays.deepEquals` để so các phần tử mảng. Trái lại, một thành phần kiểu `List` sử dụng `List.equals`, vốn so các phần tử theo thứ tự. Vì vậy tính “theo giá trị” của record vẫn phụ thuộc cách từng thành phần định nghĩa `equals`.

## 4. `hashCode()` và liên hệ với `equals`

Bản `hashCode` được tạo kết hợp thông tin mã băm từ các thành phần. Hợp đồng quan trọng:

> Nếu `a.equals(b)` trả `true` thì `a.hashCode() == b.hashCode()` phải trả `true`.

Chiều ngược lại **không được bảo đảm**: hai đối tượng không bằng nhau vẫn có thể có cùng mã băm. `HashMap` và `HashSet` dùng mã băm để tìm vùng tra cứu và tiếp tục dùng `equals` để xác định các khóa/phần tử bằng nhau.

Những điều **không được giả định**:

- Không có một công thức cố định như `Objects.hash(component1, component2)` được cam kết là thuật toán của tất cả JDK.
- Không được kiểm thử một con số mã băm cụ thể của record và kỳ vọng nó bất biến qua phiên bản hoặc lần chạy.
- `hashCode` không phải mã định danh bền vững, số kiểm tra nội dung để truyền qua mạng, hay hàm băm mật mã.
- Nếu dữ liệu ảnh hưởng tới `equals/hashCode` thay đổi sau khi đối tượng đã vào `HashSet` hoặc làm khóa `HashMap`, tìm kiếm có thể sai kỳ vọng.

Nếu tự ghi đè `equals` để bỏ qua một thành phần nhưng vẫn giữ `hashCode` mặc định dựa trên **tất cả** thành phần, ta có thể phá vỡ hợp đồng. Muốn đổi định nghĩa bằng nhau, cần đánh giá và triển khai mã băm tương ứng.

## 5. `toString()`: thuận tiện gỡ lỗi, không phải định dạng tuần tự hóa

Với đoạn:

```java
record Point(int x, int y) {}
System.out.println(new Point(4, 7));
```

Một cách hiển thị phổ biến là:

```text
Point[x=4, y=7]
```

Khi in đối tượng, Java gọi `toString()`. Bản mặc định chứa tên lớp record và tên/biểu diễn của từng thành phần, giúp đọc trạng thái nhanh hơn so với chuỗi tham chiếu chung của `Object`.

**Giới hạn quan trọng:** đặc tả quy định thông tin cần thể hiện nhưng **không cam kết cú pháp chính xác**, dấu phân cách hay khoảng trắng trong chuỗi. Không tách chuỗi `toString` để lấy giá trị, không dùng làm JSON/CSV hay hợp đồng giữa các dịch vụ. Để trao đổi dữ liệu, cần một định dạng được thiết kế và kiểm chứng riêng.

`toString` dùng biểu diễn của từng thành phần. Một mảng có thể hiển thị kiểu `[I@...` vì bản `toString` của mảng kế thừa từ `Object`, không tự liệt kê nội dung mảng. Nếu thành phần chứa bí mật hoặc dữ liệu cá nhân, in record có thể làm lộ chúng trong log; nên lựa chọn cấu trúc dữ liệu hoặc ghi đè `toString` khi cần.

## 6. Ví dụ chạy độc lập trên Java 17+

Lưu **`RecordGeneratedMethodsDemo.java`** với toàn bộ nội dung sau:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordGeneratedMethodsDemo {
    record Product(String code, int quantity) {}
    record Numbers(int[] values) {}
    record Measurement(double value) {}

    public static void main(String[] args) {
        Product first = new Product("A01", 3);
        Product second = new Product(new String("A01"), 3);
        Product changed = new Product("A01", 5);

        System.out.println("sameReference=" + (first == second));
        System.out.println("sameComponents=" + first.equals(second));
        System.out.println("differentQuantity=" + first.equals(changed));
        System.out.println("equalHash=" +
                (first.hashCode() == second.hashCode()));

        Set<Product> distinct = new HashSet<>(
                List.of(first, second, changed));
        System.out.println("uniqueProducts=" + distinct.size());

        String description = first.toString();
        System.out.println("toStringContainsComponents=" +
                (description.contains("code") &&
                 description.contains("A01") &&
                 description.contains("quantity")));

        Numbers arrayA = new Numbers(new int[] {1, 2});
        Numbers arrayB = new Numbers(new int[] {1, 2});
        System.out.println("separateArraysEqual=" +
                arrayA.equals(arrayB));

        System.out.println("nanEqual=" +
                new Measurement(Double.NaN)
                        .equals(new Measurement(Double.NaN)));
        System.out.println("signedZeroEqual=" +
                new Measurement(+0.0)
                        .equals(new Measurement(-0.0)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RecordGeneratedMethodsDemo.java
java RecordGeneratedMethodsDemo
```

Kết quả:

```text
sameReference=false
sameComponents=true
differentQuantity=false
equalHash=true
uniqueProducts=2
toStringContainsComponents=true
separateArraysEqual=false
nanEqual=true
signedZeroEqual=false
```

Các dòng in kiểm tra kết quả chắc chắn từ hợp đồng ngôn ngữ, không in một con số băm cụ thể hay giả định toàn bộ định dạng `toString`. Giải thích:

1. `first == second` sai vì hai đối tượng khác tham chiếu; `equals` đúng vì mã và số lượng bằng nhau.
2. `new String("A01")` tạo một đối tượng chuỗi độc lập nhưng có nội dung bằng `"A01"`; mặc định của record dùng phép so nội dung phù hợp.
3. `changed` khác `quantity` nên không bằng `first`. `HashSet` có hai phần tử phân biệt.
4. Hai record bằng nhau có cùng mã băm; chuỗi `toString` có tên và giá trị thành phần.
5. Hai mảng `int[]` độc lập chứa cùng `{1, 2}` nhưng `Numbers.equals` mặc định trả `false`.
6. `NaN` được xem là bằng trong thành phần số thực; `+0.0` và `-0.0` là hai giá trị không bằng nhau theo ngữ nghĩa record.

## 7. Bất biến nông: thành phần tham chiếu có thể thay đổi

Các trường thành phần của record là `final`, nhưng giá trị tham chiếu có thể trỏ tới **đối tượng thay đổi được**. Ví dụ minh họa (chưa phải chương trình hoàn chỉnh):

```java
record Cart(String owner, List<String> items) {}

List<String> source = new java.util.ArrayList<>();
source.add("book");
Cart cart = new Cart("Lan", source);

int before = cart.hashCode();
source.add("pen");
int after = cart.hashCode();
```

`Cart` vẫn giữ cùng một tham chiếu `items` nhưng nội dung `List` đổi. Vì `List.hashCode` dựa trên phần tử, việc sửa nội dung có thể làm mã băm của `Cart` thay đổi. Nếu dùng `Cart` làm khóa `HashMap`, việc tra cứu có thể không hoạt động như trước.

Đối với `List<String>`, một cách làm thực tế là tạo **bản sao không sửa được** ngay trong compact constructor:

```java
record Cart(String owner, List<String> items) {
    Cart {
        items = List.copyOf(items);
    }
}
```

`List.copyOf` tách danh sách đã lưu khỏi danh sách nguồn có thể thay đổi. Lưu ý: đây chỉ là sao chép nông ở mức danh sách; các phần tử tham chiếu có thể thay đổi bên trong vẫn cần xử lý tùy miền dữ liệu. `List.copyOf` cũng không chấp nhận phần tử `null`.

### Vì sao mảng cần xử lý riêng?

Khai báo `record Numbers(int[] values) {}` **không** tự sao chép mảng, so sâu phần tử, hay in mảng đẹp. Nếu yêu cầu là “giá trị bằng nhau khi có cùng dãy số”, hãy thiết kế một kiểu thực sự đại diện cho giá trị đó. Sau đây là một khai báo record độc lập (lưu trong tệp có `import java.util.Arrays;`):

```java
import java.util.Arrays;

record IntVector(int[] values) {
    IntVector {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof IntVector vector
                && Arrays.equals(values, vector.values);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "IntVector[values=" + Arrays.toString(values) + "]";
    }
}
```

- Constructor sao chép mảng đầu vào để người gọi không thể sửa trạng thái lưu bên trong.
- Accessor trả bản sao; không trao quyền sửa mảng nội bộ cho bên ngoài.
- `Arrays.equals` và `Arrays.hashCode` cùng dựa trên phần tử của mảng `int[]`, nên tương thích hợp đồng.
- `Arrays.toString` cung cấp biểu diễn phần tử rõ ràng. Đoạn này áp dụng cho **mảng một chiều `int[]`**; mảng lồng nhau cần lựa chọn ngữ nghĩa riêng.

Cách tùy biến này cần thiết chỉ khi thực sự muốn mảng mang **ngữ nghĩa giá trị**. Trong nhiều bài toán, dùng các thành phần bất biến hoặc `List` bất biến có thể ít mã hơn và an toàn hơn.

## 8. Khi nào giữ mặc định, khi nào tùy biến?

### 8.1. Ưu tiên giữ các phương thức sinh sẵn

Nếu **tất cả thành phần** là một phần của giá trị cần so sánh, và thành phần có `equals/hashCode` phù hợp, mặc định thường là lựa chọn tốt nhất:

```java
record Coordinate(int x, int y) {}
record OrderKey(String storeId, String orderId) {}
```

Với dữ liệu ổn định, record là ứng viên phù hợp cho giá trị truyền giữa phương thức và khóa của bộ sưu tập.

### 8.2. Chuẩn hóa trước khi gắn giá trị vào record

Nếu nghiệp vụ muốn loại bỏ khoảng trắng ở hai đầu mã, có thể chuẩn hóa ngay trong constructor, nhờ đó không cần tự định nghĩa lại ba phương thức:

```java
record ProductCode(String value) {
    ProductCode {
        value = java.util.Objects.requireNonNull(value).trim();
    }
}
```

`new ProductCode(" A01 ")` và `new ProductCode("A01")` trở thành hai đối tượng bằng nhau vì thành phần được lưu giống nhau. Chỉ chuẩn hóa khi đúng quy tắc nghiệp vụ; không tự ý bỏ khoảng trắng hoặc đổi chữ hoa/chữ thường nếu chúng có ý nghĩa.

### 8.3. Ghi đè `toString` khi không muốn in thông tin nhạy cảm

```java
record LoginContext(String username, String accessToken) {
    @Override
    public String toString() {
        return "LoginContext[username=" + username
                + ", accessToken=***]";
    }
}
```

`toString` được tùy biến để không in token. Nếu không ghi đè `equals` hay `hashCode`, hai phương thức còn lại vẫn được tạo từ **cả `username` và `accessToken`**. Ví dụ này chỉ xử lý biểu diễn chuỗi; những cách rò rỉ dữ liệu khác vẫn cần quản lý phù hợp.

### 8.4. Tùy biến `equals/hashCode` phải giữ hợp đồng

Nếu muốn thay cách nhận diện giá trị, cần xem đồng thời:

- `equals` phải có tính phản xạ, đối xứng, bắc cầu, nhất quán và trả `false` với `null`.
- `a.equals(b)` đúng thì hai mã băm **phải bằng nhau**. Nếu tùy biến so sánh mà không tùy biến hàm băm tương ứng, rất dễ phá hợp đồng.
- Bất biến riêng của record: tạo bản sao bằng các accessor của `r`, tức `new R(r.c1(), r.c2(), ...)`, thì `r.equals(copy)` phải đúng. Viết accessor trả dữ liệu khác giá trị thực sự được lưu có thể phá bất biến này.
- Bản `toString` tự tạo phải có ý nghĩa cho con người, nhưng đừng dùng chuỗi này làm định dạng API ổn định.

Trong đa số trường hợp, **thay đổi kiểu thành phần, chuẩn hóa hoặc sao chép phòng vệ** dễ kiểm soát hơn tự viết lại phép so sánh.

## 9. Lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dùng `==` để so hai record độc lập | `==` so tham chiếu | Dùng `equals` khi cần so giá trị |
| Nghĩ record so sâu mọi phần tử mảng | Mảng có `Object.equals` theo tham chiếu | Chọn kiểu giá trị phù hợp hoặc dùng `Arrays.equals/hashCode` nhất quán |
| Đặt record chứa `List` có thể sửa vào `HashSet` rồi sửa danh sách | Hash và phép so có thể đổi | Sao chép phòng vệ, giữ trạng thái thành phần ổn định |
| Ghi đè `equals` nhưng vẫn dùng mã băm mặc định không phù hợp | Phá hợp đồng với `hashCode` | Đồng bộ cả hai hoặc thiết kế lại cấu trúc record |
| Khẳng định mã băm là một số cố định | Thuật toán băm không được đặc tả cố định | Chỉ kiểm tra các quan hệ được bảo đảm |
| Đọc giá trị bằng cách phân tích `toString` | Chuỗi không có cú pháp ổn định | Sử dụng accessor hoặc định dạng trao đổi dữ liệu rõ ràng |
| Log record chứa bí mật | `toString` có thể in toàn bộ thành phần | Che dữ liệu trước khi ghi log hoặc tùy biến `toString` |
| Tưởng accessor tùy biến quyết định `equals` mặc định | Bản sinh mặc định đọc trường thành phần | Giữ accessor và invariant sao chép nhất quán |

## 10. Tự kiểm tra

1. Hai `new Point(1, 2)` độc lập có bằng nhau không? **Có** khi `Point` là cùng record khai báo `(int x, int y)`, và gọi `equals`. Chúng không cùng tham chiếu theo `==`.
2. Hai đối tượng khác nhau có thể trùng `hashCode` không? **Có**; mã băm không phải bằng chứng hai đối tượng bằng nhau.
3. `record Tag(String[] values) {}` có so từng chuỗi trong mảng không? **Không**. Mảng mặc định so tham chiếu; phải chọn giải pháp khác để so phần tử.
4. Tại sao `record Holder(List<String> v) {}` chưa chắc bất biến? Vì tham chiếu `v` không thể gán lại nhưng nội dung danh sách nguồn có thể thay đổi.
5. `toString` có thể dùng để trích xuất dữ liệu bằng cách tách dấu phẩy không? **Không nên**; cách biểu diễn không được bảo đảm là định dạng máy đọc ổn định.
6. Có nên tự viết `equals` bỏ qua `quantity` và giữ `hashCode` mặc định của `record Product(String code, int quantity)` không? **Không**: mã băm mặc định vẫn phụ thuộc `quantity` nên có thể trái với định nghĩa bằng nhau mới.

## 11. Tổng kết và nguồn tham khảo

**Ghi nhớ:** ba phương thức được tạo thể hiện **danh tính giá trị của record theo các thành phần**. `equals` kiểm tra lớp và các thành phần; `hashCode` giữ hợp đồng với `equals`; `toString` cho cách đọc dữ liệu thuận tiện. Chọn thành phần phù hợp, kiểm soát khả năng thay đổi của dữ liệu tham chiếu và cẩn thận với mảng hoặc dữ liệu nhạy cảm.

Nguồn chính thức:

- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): các thành viên tự sinh và cách khai báo tường minh.
- [Java Language Specification `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): quy tắc chính xác của `equals`, `hashCode`, `toString`.
- [Java SE 17 `java.lang.Record` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): hợp đồng và giới hạn chi tiết triển khai.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record được chuẩn hóa từ Java 16.