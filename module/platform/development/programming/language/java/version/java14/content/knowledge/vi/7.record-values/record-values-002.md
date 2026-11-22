# Hợp đồng `equals` theo kiểu record và từng thành phần

## 1. Record mô tả giá trị bằng những thành phần nào?

Một record khai báo tập dữ liệu cấu thành một giá trị ngay trong phần tiêu đề:

```java
record Product(String code, int quantity) {}
```

Ở đây `code` và `quantity` là hai **thành phần record** (record components). Java tự cung cấp các phương thức đọc `code()`, `quantity()`, constructor chính và, nếu lập trình viên không tự khai báo, phương thức `equals(Object)`.

Điểm cần hiểu: **`equals` do record tự tạo so sánh theo giá trị của toàn bộ thành phần**, thay vì chỉ so tham chiếu như `Object.equals` mặc định trong một lớp thông thường. Vì vậy hai bản ghi tạo độc lập nhưng có cùng kiểu record và cùng nội dung đều có thể được coi là bằng nhau.

```java
Product a = new Product("P01", 3);
Product b = new Product("P01", 3);

boolean sameReference = a == b;      // false
boolean sameValue = a.equals(b);     // true
```

**Phạm vi phiên bản:** Record được giới thiệu thử nghiệm ở Java 14 nhưng đã là tính năng chuẩn từ Java 16. Bài này trình bày **hợp đồng đã chuẩn hóa và còn áp dụng trong Java 17+**, không dựa trên cú pháp preview hay hành vi đã lỗi thời.

## 2. Hợp đồng tổng quát của `equals` do record tạo

Với một record `R` có các thành phần `c1, c2, ..., cn`, có thể diễn đạt kết quả `a.equals(b)` như sau:

1. Nếu `b` là `null`, trả `false`.
2. Nếu `b` không thuộc **chính cùng lớp record tại thời điểm chạy** với `a`, trả `false`.
3. Nếu `a` và `b` thuộc cùng lớp record, so sánh từng cặp **trường thành phần tương ứng**, theo quy tắc dành cho kiểu của thành phần đó.
4. Chỉ trả `true` khi **tất cả** thành phần đều bằng nhau.

Một record là `final` theo ngôn ngữ Java, do đó không thể tạo lớp con của nó để thêm thành phần rồi tham gia vào phép so sánh bằng nhau.

Ví dụ với hai record có cùng cấu trúc nhưng khác tên kiểu:

```java
record ProductId(String value) {}
record CustomerId(String value) {}

ProductId p1 = new ProductId("42");
ProductId p2 = new ProductId("42");
CustomerId c = new CustomerId("42");

boolean a = p1.equals(p2); // true
boolean b = p1.equals(c);  // false: khác lớp record
boolean d = p1.equals(null); // false
```

Hai record có các thành phần giống tên, giống kiểu và giống dữ liệu **không đương nhiên bằng nhau** nếu chúng là hai lớp record khác nhau. Đây là thuộc tính hữu ích để ngăn nhầm lẫn giữa các giá trị thuộc các miền nghiệp vụ khác nhau, chẳng hạn `ProductId` và `CustomerId`.

Một trường hợp đặc biệt: `record Marker() {}` **không có thành phần**. Mọi đối tượng cùng lớp `Marker` sẽ được coi là bằng nhau theo `equals` mặc định, vì không có thành phần nào khác nhau để làm kết quả sai.

## 3. Cách so từng thành phần tùy theo kiểu

Hợp đồng không yêu cầu tất cả thành phần phải là kiểu nguyên thủy hay kiểu bất biến. Java sử dụng các quy tắc khác nhau theo kiểu trường thành phần.

| Kiểu của một thành phần | Quy tắc tương đương của `equals` do record tạo | Hệ quả thực tế |
| --- | --- | --- |
| `byte`, `short`, `int`, `long`, `char`, `boolean` | Kết quả của `compare` trên lớp bao nguyên thủy tương ứng bằng `0` | Cùng giá trị nguyên thủy thì bằng nhau |
| `float` | Tương đương `Float.compare(a, b) == 0` | Hai `NaN` bằng nhau; `+0.0f` khác `-0.0f` |
| `double` | Tương đương `Double.compare(a, b) == 0` | Hai `NaN` bằng nhau; `+0.0` khác `-0.0` |
| `String` | Tương đương `Objects.equals(a, b)` | So nội dung chuỗi, kể cả trường hợp `null` |
| Kiểu tham chiếu khác, ví dụ `List`, record lồng nhau | Tương đương `Objects.equals(a, b)` | Tuân theo `equals` do kiểu thành phần cung cấp |
| Mảng như `int[]`, `String[]` | Tương đương `Objects.equals(a, b)`, nhưng mảng không ghi đè `Object.equals` | **So tham chiếu mảng**, không tự so sâu phần tử |

Đây là **ngữ nghĩa tương đương** theo đặc tả; không cần giả định JDK thực sự gọi từng phương thức `compare` hay `Objects.equals` theo một thứ tự cố định. Bản `equals` được tạo có thể sử dụng cách cài đặt tối ưu khác nhưng phải cho kết quả tương đương.

### 3.1. Kiểu nguyên thủy và trường hợp số thực đặc biệt

Với số nguyên, ký tự và `boolean`, kết quả thường giống trực giác “giá trị bằng nhau”. Với số thực, toán tử `==` **không phải** phép so tương đương mà record mặc định dùng:

```java
record Temperature(double value) {}

boolean nanEqual = new Temperature(Double.NaN)
        .equals(new Temperature(Double.NaN)); // true

boolean signedZeroEqual = new Temperature(+0.0)
        .equals(new Temperature(-0.0));       // false
```

Lý do:

- Theo toán tử `==` của `double`, `Double.NaN == Double.NaN` là `false`. Theo `Double.compare`, hai giá trị `NaN` được xem là bằng nhau để bảo đảm hợp đồng `equals`.
- Theo toán tử `==` của `double`, `+0.0 == -0.0` là `true`. Theo `Double.compare`, hai biểu diễn số không có dấu khác nhau sẽ **không bằng nhau**.
- Tương tự cho `float` với `Float.compare`.

Vì vậy, khi tự ghi đè `equals` cho record chứa `float` hoặc `double`, đừng thay bằng phép `==` mà không đánh giá hệ quả cho tính phản xạ và hợp đồng `hashCode`.

### 3.2. Kiểu tham chiếu và `null`

Với kiểu tham chiếu, so sánh thành phần tương đương `Objects.equals(left, right)`:

- Cả hai cùng `null` → bằng nhau.
- Một bên `null`, bên kia không → khác nhau.
- Hai bên khác `null` → dựa vào `equals` của chính đối tượng thành phần, như `String.equals` hoặc `List.equals`.

Ví dụ:

```java
record User(String name, String nickname) {}

User a = new User(new String("Lan"), null);
User b = new User("Lan", null);
User c = new User("Lan", "L");

boolean ab = a.equals(b); // true
boolean ac = a.equals(c); // false
```

`String` có thể so nội dung bằng nhau dù hai biến là hai đối tượng khác nhau. Việc một thành phần tham chiếu nhận `null` hay không phụ thuộc ràng buộc dữ liệu do bạn thiết kế; record **không tự cấm** `null`.

### 3.3. Mảng và danh sách: cùng chứa dữ liệu, cách so khác nhau

```java
record ArrayHolder(int[] values) {}
record ListHolder(java.util.List<Integer> values) {}

ArrayHolder a = new ArrayHolder(new int[] {1, 2});
ArrayHolder b = new ArrayHolder(new int[] {1, 2});

ListHolder c = new ListHolder(java.util.List.of(1, 2));
ListHolder d = new ListHolder(java.util.List.of(1, 2));

boolean arraysEqual = a.equals(b); // false
boolean listsEqual = c.equals(d);  // true
```

Hai mảng khác nhau `new int[] {1, 2}` có các phần tử như nhau nhưng **khác tham chiếu**; record mặc định không gọi `Arrays.equals`. Ngược lại, `List.equals` xác định tính bằng nhau theo các phần tử tương ứng theo thứ tự, nên hai danh sách trên bằng nhau.

Nếu hai record giữ **cùng chính một đối tượng mảng**, thành phần mảng sẽ được coi là bằng nhau. Cần phân biệt “cùng tham chiếu” với “cùng nội dung”.

Tóm lại, nói “record so sánh theo giá trị” nghĩa là nó **ủy quyền cho `equals` của từng thành phần tham chiếu**, không có phép so sâu tự động đối với mọi cấu trúc dữ liệu.

## 4. Mã Java 17+ hoàn chỉnh: kiểm tra hợp đồng bằng chương trình

Lưu tệp **`RecordEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordEqualityDemo {

    record Product(String code, int quantity, String note) {}
    record OtherProduct(String code, int quantity, String note) {}
    record Temperature(double value) {}
    record ArrayHolder(int[] values) {}
    record ListHolder(List<Integer> values) {}
    record Marker() {}

    public static void main(String[] args) {
        Product p1 = new Product("A01", 2, null);
        Product p2 = new Product(new String("A01"), 2, null);
        Product p3 = new Product("A01", 3, null);

        System.out.println("sameReference=" + (p1 == p2));
        System.out.println("sameRecordValue=" + p1.equals(p2));
        System.out.println("differentComponent=" + p1.equals(p3));
        System.out.println("nullArgument=" + p1.equals(null));
        System.out.println("differentRecordType=" +
                p1.equals(new OtherProduct("A01", 2, null)));

        Product copy = new Product(p1.code(), p1.quantity(), p1.note());
        System.out.println("copyEqual=" + p1.equals(copy));
        System.out.println("hashContract=" +
                (p1.hashCode() == p2.hashCode()));

        Set<Product> products = new HashSet<>(
                List.of(p1, p2, p3));
        System.out.println("setSize=" + products.size());

        ArrayHolder a1 = new ArrayHolder(new int[] {1, 2});
        ArrayHolder a2 = new ArrayHolder(new int[] {1, 2});
        System.out.println("distinctArraysEqual=" + a1.equals(a2));

        int[] shared = {1, 2};
        System.out.println("sharedArrayEqual=" +
                new ArrayHolder(shared).equals(new ArrayHolder(shared)));

        ListHolder l1 = new ListHolder(List.of(1, 2));
        ListHolder l2 = new ListHolder(List.of(1, 2));
        System.out.println("listsEqual=" + l1.equals(l2));

        System.out.println("nanEqual=" +
                new Temperature(Double.NaN)
                        .equals(new Temperature(Double.NaN)));
        System.out.println("signedZeroEqual=" +
                new Temperature(+0.0).equals(new Temperature(-0.0)));
        System.out.println("emptyRecordEqual=" +
                new Marker().equals(new Marker()));
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
```

Kết quả chuẩn:

```text
sameReference=false
sameRecordValue=true
differentComponent=false
nullArgument=false
differentRecordType=false
copyEqual=true
hashContract=true
setSize=2
distinctArraysEqual=false
sharedArrayEqual=true
listsEqual=true
nanEqual=true
signedZeroEqual=false
emptyRecordEqual=true
```

Đọc kết quả theo từng nhóm:

1. `p1` và `p2` độc lập nên `==` trả `false`, nhưng cùng lớp `Product` và tất cả thành phần bằng nhau, kể cả `note = null`, nên `equals` trả `true`.
2. `p3` có `quantity = 3`, khác `quantity = 2`; chỉ **một thành phần khác** là đủ khiến toàn bộ record khác nhau.
3. `OtherProduct` có phần tiêu đề giống `Product`, nhưng là **kiểu record khác**, do đó `equals` trả `false`.
4. Bản `copy` tạo từ accessor của `p1` có giá trị bằng `p1`; đó cũng là một bất biến quan trọng của record.
5. `p1` và `p2` phải có cùng mã băm vì `equals` bằng nhau; `HashSet` giữ lại hai giá trị phân biệt tương ứng với `p1/p2` và `p3`.
6. Hai mảng mới tạo khác tham chiếu nên không bằng nhau; hai record cùng trỏ `shared` thì bằng nhau; hai `List` bất biến cùng phần tử thì bằng nhau.
7. Số thực xử lý `NaN` và số không có dấu như `Double.compare`; record không thành phần `Marker` cho kết quả bằng nhau giữa hai đối tượng cùng lớp.

Không có dòng nào phụ thuộc vào số cụ thể của `hashCode` hoặc định dạng `toString`, vì những chi tiết đó không cần thiết cho việc chứng minh hợp đồng `equals`.

## 5. Hai hợp đồng phải kiểm tra khi tùy biến `equals`

Record vẫn có thể khai báo tường minh phương thức `equals(Object)`. Tuy nhiên, trước khi làm vậy cần hiểu hai nhóm quy tắc.

### 5.1. Hợp đồng chung của `Object.equals`

Một phép bằng nhau đúng cần giữ:

- **Phản xạ:** `x.equals(x)` là `true` khi `x` không phải `null`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
- **Bắc cầu:** nếu `x` bằng `y` và `y` bằng `z` thì `x` bằng `z`.
- **Nhất quán:** khi dữ liệu dùng trong phép so không thay đổi, các lần gọi trả kết quả ổn định.
- **Không bằng `null`:** `x.equals(null)` luôn là `false`.

Record mặc định được thiết kế để tuân thủ những quy tắc này **nếu các thành phần có hành vi `equals` đúng hợp đồng và dữ liệu không bị thay đổi ngoài dự kiến**.

### 5.2. Hợp đồng với `hashCode`

Nếu `x.equals(y)` là `true` thì **bắt buộc** `x.hashCode() == y.hashCode()`. Chiều ngược lại không bắt buộc: hai đối tượng khác nhau vẫn có thể trùng mã băm.

Record tự sinh `hashCode` dựa trên **tất cả** thành phần. Nếu ta ghi đè `equals` để bỏ qua một thành phần nhưng vẫn để `hashCode` mặc định kết hợp tất cả thành phần, có thể xuất hiện hai record được coi là bằng nhau nhưng có mã băm khác. Điều đó phá hợp đồng và gây lỗi khi dùng làm khóa `HashMap` hoặc phần tử `HashSet`.

**Nguyên tắc:** nếu thật sự cần định nghĩa mới về bằng nhau, hãy xem xét và ghi đè `hashCode` tương ứng; phương án đơn giản hơn thường là thay cấu trúc record để tập thành phần đúng với giá trị cần biểu diễn.

### 5.3. Bất biến sao chép của record

Bên cạnh hợp đồng chung, `java.lang.Record` yêu cầu record tôn trọng bất biến (invariant): với record `R` có accessor `c1(), ..., cn()`, khi tạo:

```java
R copied = new R(original.c1(), original.c2(), /* ... */);
```

thì `original.equals(copied)` phải là `true`, giả sử kiểu record được thiết kế đúng và không thay đổi dữ liệu giữa hai thao tác. Đoạn trên là **ký hiệu khái quát**, không phải một lớp Java đầy đủ có thể biên dịch nguyên văn.

Tránh viết accessor trả dữ liệu **khác** dữ liệu được lưu trong trường theo cách khiến đối tượng dựng lại từ accessor không còn bằng đối tượng gốc. Ví dụ xấu (chỉ minh họa):

```java
record Clamped(int value) {
    @Override
    public int value() {
        return Math.min(value, 100);
    }
}
```

Với `Clamped original = new Clamped(200)`, accessor `original.value()` trả `100`, nhưng `equals` mặc định đọc trường nội bộ `200`. Vì thế tạo `new Clamped(original.value())` sẽ ra record giữ `100` và **không bằng** `original` — vi phạm bất biến sao chép.

Nếu nghiệp vụ thực sự muốn giới hạn giá trị về `100`, hãy chuẩn hóa ngay trong constructor:

```java
record Clamped(int value) {
    Clamped {
        value = Math.min(value, 100);
    }
}
```

Lúc đó trường được lưu là `100` và accessor mặc định trả `100`; sao chép qua accessor giữ đúng giá trị. Đây là cách tiếp cận thường rõ ràng và ít rủi ro hơn ghi đè `equals`.

## 6. Bất biến nông: dữ liệu thành phần có thể thay đổi

Các trường record là `final`, nên tham chiếu trường không thể được gán lại, nhưng bản thân đối tượng mà trường trỏ tới có thể thay đổi. Điều này ảnh hưởng trực tiếp tới tính nhất quán của `equals` và `hashCode`.

Ví dụ đoạn mã minh họa đặt trong một phương thức (không phải chương trình độc lập):

```java
record Team(List<String> members) {}

List<String> names = new java.util.ArrayList<>();
names.add("Lan");

Team team = new Team(names);
Team expected = new Team(List.of("Lan"));

boolean before = team.equals(expected); // true

names.add("Mai");
boolean after = team.equals(expected);  // false
```

Hai record có thể chuyển từ bằng nhau sang khác nhau chỉ vì danh sách được tham chiếu bên trong bị sửa, dù bản thân trường `members` của record là `final`. Với những record dùng làm khóa trong `HashMap` hoặc `HashSet`, việc thay đổi thành phần có thể làm cả mã băm thay đổi và gây lỗi tra cứu.

Với `List` có phần tử bất biến như `String`, một cách xử lý là sao chép phòng vệ trong constructor:

```java
record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
```

`List.copyOf` tạo danh sách không chỉnh sửa được và tách khỏi danh sách nguồn có thể thay đổi; đây là **sao chép nông**, không tự bảo vệ các phần tử nếu chúng là đối tượng có thể thay đổi. `List.copyOf` cũng không chấp nhận phần tử `null`.

### 6.1. Cần bằng nhau theo nội dung mảng thì làm sao?

Mặc định `record Bytes(byte[] data) {}` so mảng theo tham chiếu. Nếu “cùng chuỗi byte” mới là ý nghĩa giá trị cần thiết, phải có thiết kế bổ sung. Ví dụ sau có constructor/accessor sao chép mảng và tùy biến `equals` đồng bộ với `hashCode`:

```java
import java.util.Arrays;

record Bytes(byte[] data) {
    Bytes {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes b
                && Arrays.equals(data, b.data);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }
}
```

Đây là một **kiểu record độc lập** có thể đặt trong tệp `Bytes.java` cùng dòng `import`. Hàm `Arrays.equals(byte[], byte[])` so nội dung phần tử; `Arrays.hashCode(byte[])` tính mã băm tương thích; hai bản sao mảng khác nhau chứa cùng byte sẽ được coi là bằng nhau. Việc sao chép đầu vào và khi đọc giúp tránh thay đổi mảng nội bộ từ bên ngoài.

Nếu chỉ ghi đè accessor để trả `data.clone()` nhưng giữ `equals` mặc định dựa trên **tham chiếu mảng**, thao tác sao chép record qua accessor rất dễ phá bất biến record. Khi chọn mảng làm thành phần record, cần thiết kế **cả phép so lẫn biên giới thay đổi dữ liệu**.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Hai record có cấu trúc giống nhau thì bằng nhau” | `equals` đòi hỏi đúng **cùng lớp record** | So cùng kiểu trước, so thành phần sau |
| “Record luôn so mọi tham chiếu bằng `==`” | `String`, `List`, record lồng nhau dùng `equals` riêng | Tham chiếu dùng ngữ nghĩa tương đương `Objects.equals` |
| “Record so sâu phần tử mảng” | Mảng không ghi đè `Object.equals` | Cần `Arrays.equals` hoặc kiểu giá trị phù hợp |
| “Mọi số thực cùng giá trị số theo `==` đều bằng nhau” | `Double.compare` phân biệt `+0.0` / `-0.0` | Kiểm tra quy tắc wrapper compare |
| “Hai `NaN` không thể bằng nhau” | `Double.compare(NaN, NaN) == 0` | Record mặc định cho `NaN` bằng nhau |
| “Có thể bỏ một thành phần khi ghi đè `equals` mà không quan tâm `hashCode`” | Hai object bằng nhau có thể băm khác nhau | Đồng bộ hợp đồng `equals/hashCode` |
| “Trường `final` bảo đảm mọi thứ bên trong bất biến” | Đối tượng tham chiếu có thể thay đổi | Kiểm soát và sao chép thành phần mutable |
| “Accessor tùy biến được gọi bởi `equals` mặc định” | Bản được tạo đọc trường thành phần, không gọi accessor | Tránh accessor làm lệch bất biến sao chép |

## 8. Bài tập tự kiểm tra

**Bài 1.** Cho `record Code(String text) {}`. So `new Code(new String("abc"))` với `new Code("abc")` bằng `equals`. **Kết quả `true`** vì cùng kiểu record và `String.equals` so nội dung.

**Bài 2.** Cho `record Pair(int x, int y) {}`. So `new Pair(2, 4)` với `new Pair(2, 5)`. **Kết quả `false`** vì một thành phần khác nhau là đủ.

**Bài 3.** Cho `record A(int value) {}` và `record B(int value) {}`. `new A(1).equals(new B(1))` là **`false`** dù có cùng dữ liệu, do khác lớp record.

**Bài 4.** Cho `record Data(int[] values) {}`. So hai `Data` chứa hai mảng mới tạo `{1, 2}`. **Kết quả `false`**, vì trường mảng được so theo tham chiếu.

**Bài 5.** Cho `record Score(double n) {}`. `new Score(-0.0).equals(new Score(+0.0))` trả **`false`**. `new Score(Double.NaN).equals(new Score(Double.NaN))` trả **`true`**.

**Bài 6.** Record có `List` thành phần dùng làm khóa `HashMap`. Sau khi thêm phần tử vào danh sách gốc, có bảo đảm tra cứu khóa vẫn hoạt động như trước không? **Không**. `equals` và `hashCode` có thể đổi theo danh sách.

**Bài 7.** Tùy biến accessor của `record Limited(int n)` để trả số đã giới hạn, nhưng trường lưu vẫn là giá trị chưa giới hạn, có rủi ro gì? **Có thể vi phạm bất biến sao chép** khi dựng record mới từ accessor của record cũ.

## 9. Tóm tắt và tài liệu tham khảo

Với record được tạo mặc định, phép so bằng nhau phụ thuộc **(1) cùng lớp record, (2) tất cả thành phần bằng nhau theo kiểu của chúng**. Số nguyên, số thực, tham chiếu, `null` và mảng có những quy tắc khác nhau. Record cung cấp phép so theo cấu trúc giá trị, nhưng **không tự tạo so sánh sâu cho mảng và không tự làm dữ liệu tham chiếu trở nên bất biến**.

Khi cần tùy biến, bảo đảm hợp đồng chung của `equals`, tính nhất quán với `hashCode` và bất biến sao chép của record. Thiết kế thành phần phù hợp hoặc chuẩn hóa trong constructor thường đơn giản hơn tự viết lại phép so.

Tài liệu chuẩn (hành vi còn hiệu lực trên Java hiện đại):

- [Java SE 21 — `java.lang.Record`, phần `equals(Object)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): quy tắc cùng kiểu record và so thành phần; bất biến sao chép.
- [Java Language Specification Java SE 17 `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): thành viên tự sinh, so số thực và truy cập trường.
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): cách khai báo record đã chuẩn hóa và ví dụ sử dụng.
- [Java SE 21 — `Objects.equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): so sánh kiểu tham chiếu có thể nhận `null`.