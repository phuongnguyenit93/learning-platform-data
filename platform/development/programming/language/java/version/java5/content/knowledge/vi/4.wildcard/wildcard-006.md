# Nguyên tắc nguồn cung cấp và nơi tiếp nhận dữ liệu theo PECS

## 1. PECS giải quyết bài toán gì?

Khi viết phương thức xử lý một tập hợp, ta thường cần nhận dữ liệu từ nhiều kiểu phần tử có quan hệ kế thừa. Ví dụ, một phương thức tính tổng có thể đọc cả `List<Integer>` và `List<Double>`; một phương thức sao chép cần đưa số nguyên vào `List<Number>` hoặc `List<Object>`.

Nếu mọi tham số đều dùng `List<Number>`, API sẽ quá chặt. Nếu bỏ thông tin kiểu để truyền tùy ý, trình biên dịch mất khả năng bảo vệ dữ liệu. Wildcard giúp mô tả chính xác phần linh hoạt cần thiết.

**PECS** là cách nhớ **Producer Extends, Consumer Super**:

- **Nguồn cung cấp (producer)** đưa ra các giá trị để phương thức sử dụng: ưu tiên `? extends T`.
- **Nơi tiếp nhận (consumer)** nhận các giá trị `T` do phương thức đưa vào: ưu tiên `? super T`.

Phải xét vai trò **từ bên trong phương thức đang thiết kế**, đối với một kiểu dữ liệu `T` cụ thể. Một danh sách không có vai trò cố định suốt chương trình.

PECS áp dụng cho thiết kế generic trong Java hiện nay. Các ví dụ hoàn chỉnh dưới đây chạy với JDK 17 trở lên; ta dùng API hiện đại, không cần kiểu thô hay ép kiểu không được kiểm tra.

## 2. Vì sao không truyền thẳng List<Integer> vào List<Number>?

`Integer` là kiểu con của `Number`, nhưng `List<Integer>` không phải kiểu con của `List<Number>`. Đây là tính **bất biến (invariance)** của tham số kiểu.

Đoạn sau minh họa lỗi biên dịch; không phải chương trình chạy độc lập:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Khong bien dich
// numbers.add(2.5);                // Neu duoc phep, danh sach Integer bi chen Double
```

Đặt giả thuyết phép gán được cho phép: người giữ `numbers` có quyền thêm `Double` vì `Double` cũng là `Number`. Nhưng người giữ `integers` lại tin mọi phần tử đều là `Integer`. Java chặn phép gán để ngăn mâu thuẫn này từ lúc biên dịch.

Wildcard không biến `List<Integer>` thành `List<Number>`. Nó tạo một cách nhìn với các thao tác được giới hạn theo thông tin kiểu còn biết.

```java
List<Integer> integers = new ArrayList<>(List.of(10, 20));
List<? extends Number> source = integers;
Number first = source.get(0); // Doc an toan duoi dang Number
```

Đây là một đoạn minh họa, cần import `java.util.List` và `java.util.ArrayList` khi đặt vào chương trình.

## 3. Nguồn cung cấp: đọc T qua ? extends T

### 3.1. Ý nghĩa của giới hạn trên

`List<? extends Number>` có nghĩa là “danh sách của một kiểu chưa biết, nhưng kiểu đó là `Number` hoặc một kiểu con của `Number`”.

Có thể truyền vào:

- `List<Integer>`.
- `List<Double>`.
- `List<Number>`.

Mọi phần tử đọc ra đều có thể được nhìn dưới kiểu `Number`. Phương thức chỉ cần các khả năng mà `Number` cung cấp, chẳng hạn `doubleValue()`.

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number value : source) {
        total += value.doubleValue();
    }
    return total;
}
```

Đây là khai báo phương thức minh họa bên trong một lớp. Hợp đồng đơn giản ở đây giả định danh sách và các phần tử đều khác `null`. Phép cộng `double` là ví dụ về generic, không phải cách tính tiền với độ chính xác thập phân.

### 3.2. Vì sao không thêm một Number vào nguồn?

```java
List<? extends Number> source = new ArrayList<Integer>();

// source.add(Integer.valueOf(1)); // Khong bien dich
// source.add(Double.valueOf(2));  // Khong bien dich
// source.add(new Object());       // Khong bien dich
```

Biến `source` cũng có thể trỏ tới `List<Double>`. Trình biên dịch không biết kiểu phần tử cụ thể, nên không thể bảo đảm một `Integer` được chấp nhận. Ngay cả `Number` cũng quá rộng: danh sách thực tế có thể chỉ nhận `Integer`.

Điều quan trọng là **thông tin của kiểu tham chiếu tại vị trí gọi**, không phải việc lập trình viên nhìn thấy biểu thức `new ArrayList<Integer>()` ngay phía trước.

### 3.3. “Nguồn cung cấp” không có nghĩa “bất biến”

`? extends T` giới hạn việc đưa **giá trị mới không rỗng** vào vị trí phần tử của kiểu chưa biết. Nó không khóa danh sách.

Ví dụ dưới đây có thể biên dịch và chạy với `ArrayList`:

```java
List<Integer> original = new ArrayList<>(List.of(10, 20));
List<? extends Number> source = original;

source.remove(0); // Co the xoa phan tu
source.clear();   // Co the xoa tat ca
```

Một số điểm cần phân biệt:

- `source.add(null)` được hệ thống kiểu chấp nhận, nhưng đối tượng thực tế có thể cấm `null` hoặc cấm thêm phần tử.
- `remove`, `clear` hoặc xóa qua bộ lặp có thể được hỗ trợ; nếu không, thao tác có thể ném `UnsupportedOperationException`.
- Đọc được một tham chiếu không làm cho đối tượng phần tử trở nên bất biến.
- Tham chiếu khác vẫn có thể thay đổi danh sách gốc nếu đối tượng cho phép.

Vì vậy, PECS mô tả **quan hệ kiểu cho dòng dữ liệu**, không cung cấp tính bất biến hay an toàn luồng.

## 4. Nơi tiếp nhận: đưa T vào ? super T

### 4.1. Ý nghĩa của giới hạn dưới

`List<? super Integer>` là danh sách của một kiểu chưa biết nhưng kiểu đó là `Integer` hoặc một kiểu cha của `Integer`.

Các trường hợp thông dụng được chấp nhận:

- `List<Integer>`.
- `List<Number>`.
- `List<Object>`.

Cả ba đều có thể chứa một `Integer` mà không vi phạm hợp đồng kiểu phần tử.

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Hai số nguyên được tự động đóng hộp thành `Integer`. Phương thức có thể thêm chúng mà không cần ép kiểu. Danh sách đích phải hỗ trợ thao tác thêm.

### 4.2. Vì sao đọc ra chỉ bảo đảm Object?

```java
List<Object> mixed = new ArrayList<>();
mixed.add("existing");
List<? super Integer> destination = mixed;

destination.add(10);
Object first = destination.get(0);

// Integer number = destination.get(0); // Khong bien dich
```

`destination` có thể là `List<Object>` đã chứa chuỗi, hoặc `List<Number>` đã chứa `Double`. Giới hạn dưới bảo đảm nó **nhận được `Integer`**, không bảo đảm tất cả dữ liệu bên trong đều là `Integer`.

Ta vẫn đọc được dữ liệu, nhưng kiểu tĩnh an toàn tổng quát chỉ là `Object`. Ép kiểu về `Integer` không phải cách sửa thiết kế: phép ép có thể thất bại lúc chạy.

### 4.3. Consumer super không cho thêm mọi kiểu cha

```java
List<? super Integer> destination = new ArrayList<Number>();

destination.add(7); // Duoc
// destination.add(7.5); // Khong bien dich
// destination.add("x"); // Khong bien dich
```

Biến đích có thể trỏ tới `List<Integer>`, nên `Double` không an toàn. Chữ `super` mô tả **các kiểu danh sách có thể được nhận làm đối số**, không mở quyền thêm mọi kiểu cha hoặc mọi đối tượng.

Tổng quát, `? super T` cho phép truyền giá trị có thể gán cho `T`, gồm `T` và các kiểu con của `T`.

## 5. Cách chọn chữ ký phương thức

Bắt đầu bằng câu hỏi: “Phương thức cần lấy giá trị gì ra và đưa giá trị gì vào tham số này?”

| Nhu cầu đối với phần tử | Kiểu tham số thường dùng | Điều được bảo đảm |
| --- | --- | --- |
| Lấy phần tử ra để xử lý như `T` | `List<? extends T>` | Đọc được `T`; không tùy ý thêm một `T` mới |
| Đưa các giá trị `T` vào | `List<? super T>` | Ghi được `T`; đọc tổng quát là `Object` |
| Đọc và ghi với cùng một kiểu phần tử có quan hệ rõ ràng | `List<T>` trong phương thức generic | Duy trì một kiểu `T` xuyên suốt thao tác |
| Chỉ cần kích thước, kiểm tra rỗng hoặc nhìn phần tử như `Object` | `List<?>` | Không cần đặt một giới hạn cụ thể |

Bảng mô tả khả năng **kiểm tra kiểu**; mọi thao tác sửa còn phụ thuộc hợp đồng của đối tượng thực tế.

### 5.1. Tham số đầu vào không tự động là producer

Trong `addDefaults(destination)`, `destination` cũng được truyền vào phương thức, nhưng nó nhận dữ liệu do phương thức tạo ra. Vì vậy, nó là consumer.

Ngược lại, một danh sách “kết quả từ cơ sở dữ liệu” trở thành producer khi phương thức hiện tại đọc từng phần tử của nó.

Đừng chọn `extends` chỉ vì tham số nằm trong ngoặc của lời gọi. Hãy vẽ hướng đi của **phần tử**, không phải hướng truyền tham chiếu.

### 5.2. Khi cần cả đọc và ghi, dùng quan hệ T

Phương thức dưới đây đọc phần tử đầu, ghi một phần tử thay thế cùng kiểu và trả về giá trị cũ:

```java
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
```

Đây là khai báo phương thức minh họa. Danh sách phải có ít nhất một phần tử và hỗ trợ `set`.

`<T>` đặt tên cho một kiểu có quan hệ giữa danh sách, đối số thay thế và kết quả trả về. Hai wildcard độc lập không thể hiện được quan hệ đó.

Cũng không nên hiểu máy móc rằng cứ có đọc lẫn sửa là tuyệt đối cấm wildcard: các thao tác như hoán đổi có thể dùng kỹ thuật bắt giữ wildcard. Ở bước thiết kế API, hãy hỏi có cần liên kết cùng một kiểu giữa nhiều vị trí hay không; nếu có, một tham số kiểu được đặt tên thường rõ ràng hơn.

## 6. Ví dụ hoàn chỉnh: chuyển phần tử từ nguồn sang đích

Mục tiêu: viết một phương thức nhận nguồn có phần tử là `T` hoặc kiểu con, và thêm các phần tử đó vào đích có thể chứa `T`.

Dòng dữ liệu:

```text
source: Iterable<? extends T>
               |
               | doc mot phan tu nhu T
               v
            bien T
               |
               | dua T vao dich
               v
destination: Collection<? super T>
```

Ta dùng `Iterable` cho nguồn vì chỉ cần duyệt, và `Collection` cho đích vì chỉ cần `add`. Không bắt buộc cả hai phải là `List`.

Lưu dưới tên `PecsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class PecsDemo {
    static double sum(Iterable<? extends Number> source) {
        double total = 0;
        for (Number value : source) {
            total += value.doubleValue();
        }
        return total;
    }

    static <T> void appendAll(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static void addDefaults(Collection<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static <T> T replaceFirst(List<T> values, T replacement) {
        return values.set(0, replacement);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(0.5, 1.5);

        System.out.println("sum integers = " + sum(integers));
        System.out.println("sum decimals = " + sum(decimals));

        List<Number> numbers = new ArrayList<>();
        PecsDemo.<Number>appendAll(integers, numbers);
        PecsDemo.<Number>appendAll(decimals, numbers);
        System.out.println("numbers = " + numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(integers, objects);
        System.out.println("objects = " + objects);

        List<Number> defaults = new ArrayList<>();
        addDefaults(defaults);
        System.out.println("defaults = " + defaults);

        List<Number> writable = new ArrayList<>(List.<Number>of(1, 2));
        Number old = replaceFirst(writable, 2.5);
        System.out.println("replace = " + old + " -> " + writable);

        List<Number> copyTarget = new ArrayList<>(List.<Number>of(0, 0, 0));
        Collections.copy(copyTarget, integers);
        System.out.println("copy = " + copyTarget);

        List<Integer> sorted = new ArrayList<>(List.of(3, 1, 2));
        Comparator<Number> byValue =
                Comparator.comparingDouble(Number::doubleValue);
        sorted.sort(byValue);
        System.out.println("sorted = " + sorted);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all PecsDemo.java
java PecsDemo
```

Stdout:

```text
sum integers = 6.0
sum decimals = 2.0
numbers = [1, 2, 3, 0.5, 1.5]
objects = [1, 2, 3]
defaults = [10, 20]
replace = 1 -> [2.5, 2]
copy = [1, 2, 3]
sorted = [1, 2, 3]
```

### Giải thích điểm cốt lõi

1. `sum` lấy `Number` từ nguồn nên nhận được cả số nguyên và số thực.
2. Khi `T = Number`, nguồn `List<Integer>` hay `List<Double>` đều phù hợp với `? extends Number`, còn `List<Number>` nhận các phần tử qua `? super Number`.
3. `List<Object>` có thể làm đích của luồng `Integer`. Nó đủ rộng để giữ mọi số nguyên được đưa vào.
4. `replaceFirst` dùng một kiểu `T` có tên. Với `List<Number>`, giá trị thay thế có thể là `Double` và giá trị trả về được nhìn như `Number`.
5. `List.of(...)` chỉ làm nguồn trong chương trình; nơi cần thêm hoặc thay phần tử đều dùng `ArrayList`.

Hai lời gọi `PecsDemo.<Number>appendAll(...)` chỉ rõ tham số kiểu để người học theo dõi. Trong các trường hợp này, bỏ `<Number>` vẫn cho phép trình biên dịch suy luận kiểu phù hợp.

`appendAll` giả định các đối số khác `null`, đích hỗ trợ `add`, và nguồn không bị thay đổi trong lúc duyệt. Không truyền cùng một danh sách làm cả nguồn lẫn đích: việc vừa lặp vừa thêm có thể gây `ConcurrentModificationException`. Phương thức sao chép các tham chiếu phần tử; không tạo bản sao sâu của từng đối tượng.

## 7. Quan hệ giữa hai phía: không phải hai wildcard tùy ý

Chữ ký quan trọng là:

```java
static <T> void appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination)
```

Nó biểu diễn một cầu nối:

```text
kieu phan tu nguon <= T <= kieu phan tu dich
```

Ở đây, `<=` diễn tả quan hệ có thể gán theo kiểu tham chiếu, không phải so sánh số.

Ví dụ:

| Nguồn | Đích | Có thể gọi? | Lý do |
| --- | --- | --- | --- |
| `List<Integer>` | `List<Integer>` | Có | Chọn `T = Integer` |
| `List<Integer>` | `List<Number>` | Có | Số nguyên có thể được giữ dưới kiểu `Number` |
| `List<Double>` | `List<Object>` | Có | Số thực có thể được giữ dưới kiểu `Object` |
| `List<Number>` | `List<Integer>` | Không | Nguồn có thể chứa `Double` |
| `List<String>` | `List<Number>` | Không | Chuỗi không thể được đưa vào danh sách số |

`appendAll(List<?>, List<?>)` không tạo cầu nối kiểu đó. Việc cả hai đều dùng dấu `?` không có nghĩa chúng có chung một kiểu chưa biết.

PECS cũng không thực hiện chuyển đổi số: `List<Integer>` không thể được thêm thẳng vào `List<Long>` chỉ vì giá trị nguyên nhỏ có thể biểu diễn bằng `long`. Muốn đổi `Integer` thành `Long` phải có thao tác chuyển đổi riêng.

## 8. Nhận ra PECS trong API Java hiện nay

### 8.1. Collections.copy: cùng quan hệ kiểu, khác cách ghi

Chữ ký API:

```java
public static <T> void copy(List<? super T> dest, List<? extends T> src)
```

`src` cung cấp phần tử, `dest` tiếp nhận phần tử. **Thứ tự đối số là đích trước, nguồn sau**, khác `appendAll` trong ví dụ của bài.

`Collections.copy` thay thế các phần tử đã có tại các vị trí đầu của đích. Đích phải có `size() >= src.size()` và hỗ trợ `set`. Nó không tự tăng kích thước như `appendAll`. Ví dụ chạy phía trên khởi tạo ba phần tử `0` trước khi sao chép. Đây là hợp đồng của [Collections.copy trong Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)).

Đoạn dưới đây biên dịch nhưng thất bại lúc chạy:

```java
List<Integer> source = List.of(1, 2, 3);
List<Number> target = new ArrayList<>(3);
// Collections.copy(target, source); // IndexOutOfBoundsException
```

`new ArrayList<>(3)` đặt dung lượng ban đầu, nhưng `size()` vẫn bằng `0`. Đủ dung lượng bộ nhớ không có nghĩa đã có đủ phần tử để thay thế.

### 8.2. Comparator nhận phần tử để so sánh

Trong ví dụ hoàn chỉnh, `Comparator<Number>` sắp xếp được `List<Integer>`.

Bộ so sánh **nhận** hai phần tử của danh sách làm đối số. Một bộ so sánh xử lý được mọi `Number` cũng xử lý được `Integer`. Đây là lý do tham số bộ so sánh của thao tác sắp xếp có dạng `Comparator<? super E>`, với `E` là kiểu phần tử của danh sách.

Chiều ngược lại không an toàn: `Comparator<Integer>` không thể xử lý mọi phần tử của `List<Number>`, vì danh sách đó có thể chứa `Double`. Bản thân `Comparator<T>` mô tả kiểu đối số nó nhận qua `compare(T, T)`; xem [API Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

PECS không chỉ áp dụng cho nơi lưu trữ. Nó còn giúp đọc các API nhận hành vi: tham số hàm tiếp nhận dữ liệu và kết quả hàm cung cấp dữ liệu.

## 9. Giới hạn kiểu và khả năng thay đổi là hai hợp đồng riêng

Đoạn sau minh họa một lỗi lúc chạy, không phải lỗi generic:

```java
List<Integer> fixed = List.of(1, 2);
List<? super Integer> destination = fixed;
// destination.add(3); // UnsupportedOperationException
```

Hệ thống kiểu cho phép thêm `Integer` qua `? super Integer`. Nhưng đối tượng do `List.of` tạo ra không hỗ trợ thao tác thêm.

Khi thiết kế phương thức ghi, cần nêu rõ yêu cầu về thao tác được hỗ trợ. Wildcard không thể bảo đảm rằng một tập hợp thực sự có thể thay đổi. Hợp đồng [Collection của Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html) quy định một số thao tác sửa là tùy chọn.

Tương tự, một danh sách `ArrayList` có thể được thay đổi qua tham chiếu khác dù tham số hiện tại mang kiểu `? extends T`. Nếu yêu cầu nghiệp vụ là bảo vệ cấu trúc khỏi thay đổi, phải chọn cơ chế phù hợp riêng; PECS không thay thế yêu cầu đó.

## 10. Những lỗi thiết kế thường gặp

### Dùng List<T> ở cả hai phía khi muốn sao chép linh hoạt

```java
static <T> void strictCopy(List<T> source, List<T> destination) {
    destination.addAll(source);
}
```

Chữ ký này buộc hai danh sách cùng tham số kiểu. Nó không nhận cặp `List<Integer>` và `List<Number>`. Đổi thành nguồn `? extends T` và đích `? super T` thể hiện đúng quan hệ cần thiết.

### Dùng ? extends T cho đích rồi ép kiểu để thêm

Nếu công việc chính là đưa `T` vào đích, hãy mô tả đích bằng `? super T`. Ép kiểu để vượt giới hạn có thể phá an toàn dữ liệu và tạo cảnh báo không được kiểm tra.

### Cho rằng ? super Integer trả về Integer

Đích có thể là `List<Object>` chứa dữ liệu khác kiểu. Nếu cần lấy đúng giá trị vừa thêm, giữ tham chiếu `Integer` đó riêng hoặc thiết kế một kết quả trả về có kiểu rõ ràng; không suy luận toàn bộ đích chỉ chứa số nguyên.

### Trả về wildcard theo thói quen

Một phương thức tự tạo danh sách kết quả thường nên trả `List<T>` thay vì `List<? extends T>` khi kiểu chính xác đã biết. Wildcard trong kiểu trả về có thể đẩy việc xử lý kiểu chưa biết sang người gọi. Đây là lựa chọn thiết kế tùy hợp đồng, không phải lệnh cấm tuyệt đối.

### Xem PECS là quy tắc chọn theo tên biến

Tên `input`, `output`, `source` hay `target` chỉ là gợi ý. Cần xem phương thức thực sự đọc và ghi giá trị thuộc kiểu nào. Một cấu trúc cũng có thể là nguồn trong một phương thức và đích trong phương thức khác.

## 11. Tự kiểm tra

### Bài 1: Hoàn thiện chữ ký

Cần viết phương thức `collect` duyệt nguồn, thêm từng phần tử vào đích. Điền giới hạn:

```java
static <T> void collect(
        Iterable<? ... T> source,
        Collection<? ... T> destination)
```

**Đáp án:** nguồn dùng `extends`, đích dùng `super`. Giá trị lấy ra như `T` có thể được đưa an toàn vào nơi nhận `T`.

### Bài 2: Đọc và ghi với giới hạn dưới

Với `List<? super Integer> values`:

- Có thể thêm `Integer` không?
- Có thể thêm `Double` không?
- Có thể gán `values.get(0)` trực tiếp cho biến `Integer` không?

**Đáp án:** hệ thống kiểu cho phép thêm `Integer`; không cho thêm `Double`; đọc tổng quát chỉ bảo đảm `Object`. Thao tác thêm thực tế còn phụ thuộc đối tượng hỗ trợ thay đổi hay không.

### Bài 3: Phương thức sao chép nhận cặp nào?

```java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = new ArrayList<>();
```

- `appendAll(integers, numbers)`: hợp lệ, `Number` chứa được `Integer`.
- `appendAll(numbers, integers)`: không biên dịch, `Number` có thể là `Double`.

Không dựa vào việc hai danh sách đang rỗng để cho phép lời gọi thứ hai. Kiểm tra kiểu dựa trên hợp đồng kiểu của tham chiếu, không dựa vào nội dung tại một thời điểm.

### Bài 4: Nguồn có được clear không?

```java
List<? extends Number> source = new ArrayList<Integer>();
source.clear();
```

**Đáp án:** đoạn này hợp lệ và `ArrayList` hỗ trợ thao tác đó. `extends` không biến danh sách thành bất biến. Điều bị giới hạn là khả năng đưa giá trị mới vào kiểu phần tử chưa biết.

Khi đọc một chữ ký generic, hãy xác định `T`, theo dõi dòng phần tử, rồi kiểm tra quyền đọc và ghi của từng tham số. Cách suy luận đó giúp dùng PECS chính xác hơn việc chỉ học thuộc hai từ khóa.
