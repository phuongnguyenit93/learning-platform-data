# Tính bất biến của lớp bao và phép tăng giảm

## 1. Vì sao Integer bất biến nhưng vẫn viết được counter++?

Đối tượng của các lớp bao chuẩn như `Integer` và `Long` không cung cấp cơ chế đổi giá trị số đang được giữ trong chính đối tượng đó. Một khi một `Integer` biểu diễn 10, nó không được sửa thành một `Integer` biểu diễn 11.

Tuy nhiên, **đối tượng bất biến** không có nghĩa **biến tham chiếu không được gán lại**. Biến `Integer counter` có thể đang giữ tham chiếu tới wrapper biểu diễn 10 rồi được gán một tham chiếu biểu diễn 11.

```java
Integer counter = 10;
counter++;
```

`counter++` không phải lời gọi sửa trường bên trong `Integer`. Java cho phép phép tăng trên biến wrapper số bằng cách kết hợp mở hộp, tính toán, đóng hộp và gán kết quả trở lại biến.

Đây là điểm cần tách thành hai cấp:

| Thành phần | Có gì thay đổi trong counter++? |
| --- | --- |
| Đối tượng wrapper ban đầu | Không bị đổi giá trị bên trong |
| Giá trị số dùng để tính | Được lấy ra qua unboxing rồi tăng theo quy tắc số học |
| Biến counter | Được gán tham chiếu tới wrapper biểu diễn kết quả |
| Biến khác giữ wrapper ban đầu | Không tự trỏ theo biến counter |

Các ví dụ trong bài dùng những cơ chế vẫn được áp dụng trong Java hiện hành và chạy bằng JDK 17 trở lên.

## 2. Đường đi của một phép tăng trên Integer

Nếu chỉ xét tác dụng cập nhật biến `Integer` và không dùng giá trị trả về của biểu thức, có thể hiểu:

```java
counter++;
```

theo các bước ý nghĩa:

1. Đọc tham chiếu hiện tại trong biến `counter`.
2. Mở hộp để lấy giá trị `int`.
3. Cộng 1 theo quy tắc số học của `int`.
4. Boxing kết quả thành một wrapper phù hợp.
5. Lưu tham chiếu kết quả trở lại biến `counter`.

Với biến `Integer`, có thể viết dạng tường minh minh họa tác dụng cập nhật:

```java
counter = Integer.valueOf(counter.intValue() + 1);
```

Đây là cách giải thích cho biến `Integer` đơn giản, không phải công thức thay thế mọi biểu thức tăng ở mọi kiểu. Cần phân biệt thêm kết quả của tiền tố/hậu tố và quy tắc thu hẹp ở những wrapper nhỏ như `Byte`.

Boxing kết quả không đồng nghĩa mỗi lần phải cấp phát một đối tượng mới riêng. Wrapper có thể được tái sử dụng theo cơ chế của API/JVM; điều cốt lõi là không sửa giá trị của đối tượng ban đầu.

Đối chiếu quy tắc tăng tại [JLS §15.14.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.14.2).

## 3. Tiền tố, hậu tố và giá trị của biểu thức

| Biểu thức | Giá trị được biểu thức cung cấp | Giá trị được lưu lại trong biến |
| --- | --- | --- |
| `x++` | Giá trị trước khi tăng | Kết quả tăng |
| `++x` | Kết quả sau khi tăng | Kết quả tăng |
| `x--` | Giá trị trước khi giảm | Kết quả giảm |
| `--x` | Kết quả sau khi giảm | Kết quả giảm |

Với wrapper, kiểu của biểu thức tăng/giảm vẫn là kiểu của biến theo quy tắc của toán tử. Việc tính toán bên trong có thể dùng unboxing và chuyển đổi số thích hợp.

```java
Integer counter = 1000;
Integer alias = counter;
Integer previous = counter++;
```

Sau đoạn này, `previous` nhận giá trị tham chiếu mà `counter` đã giữ trước phép tăng, nên cùng tham chiếu với `alias`. Cả hai vẫn biểu diễn 1000. Biến `counter` đã được cập nhật để biểu diễn 1001.

```java
Integer current = ++counter;
```

Tiền tố cập nhật biến trước rồi cung cấp kết quả đã cập nhật. Sau đó `current` và `counter` biểu diễn 1002 trong ví dụ này.

Không suy từ cú pháp ngắn mà gộp nhiều phép tăng cùng một biến trong một biểu thức khó đọc. Viết riêng bước cập nhật và bước sử dụng kết quả thường giúp thấy rõ giá trị cũ/mới, đặc biệt khi có wrapper và khả năng `null`.

Quy tắc tiền tố được nêu tại [JLS §15.15.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.15.1); phép giảm tuân theo hướng trừ tương ứng.

## 4. Tham chiếu chia sẻ không tự được cập nhật

### 4.1. Một alias vẫn giữ wrapper cũ

```java
Integer first = 10;
Integer second = first;
first++;
```

`second` không tự chuyển thành 11. Phép tăng ghi lại biến `first`; nó không đi tìm và thay tất cả các biến khác từng tham chiếu tới cùng wrapper.

Đây là một lợi ích của tính bất biến: những nơi đang dùng wrapper cũ không thấy giá trị bên trong đối tượng đột ngột thay đổi bởi một biến khác.

### 4.2. Tăng tham số trong hàm không đổi biến của người gọi

```java
static void incrementLocally(Integer value) {
    value++;
}
```

Khi truyền một `Integer` vào phương thức, giá trị tham chiếu được sao chép vào biến tham số. Phép tăng chỉ cập nhật biến tham số cục bộ; wrapper ban đầu không bị sửa và biến ở nơi gọi không được gán lại.

Nếu cần nơi gọi nhận giá trị tăng, có thể thiết kế phương thức trả về kết quả rồi gán kết quả vào biến của nơi gọi. Đừng dùng `Integer` như một “hộp số sửa được” chỉ vì nó là kiểu đối tượng.

### 4.3. Tăng biến for-each không cập nhật List

```java
for (Integer value : values) {
    value++;
}
```

`value` là biến cục bộ của lượt duyệt. Phép tăng tạo ra kết quả để gán lại biến ấy, không thay phần tử mà danh sách đang lưu.

Để giữ kết quả mới trong một `List<Integer>` có thể sửa, cần dùng API cập nhật, chẳng hạn `set` theo chỉ số hoặc `replaceAll` phù hợp. Vấn đề không nằm ở việc thiếu một phép tăng “mạnh hơn”, mà ở chỗ biến nào được ghi trở lại.

## 5. Chương trình chạy đầy đủ

Lưu thành `ImmutableWrapperUpdateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableWrapperUpdateDemo {
    static void incrementLocally(Integer value) {
        value++;
    }

    public static void main(String[] args) {
        Integer counter = 1000;
        Integer alias = counter;
        Integer previous = counter++;
        System.out.println("postfix previous=" + previous);
        System.out.println("postfix counter=" + counter);
        System.out.println("alias=" + alias);
        System.out.println("previous is alias=" + (previous == alias));

        Integer current = ++counter;
        System.out.println("prefix current=" + current);
        System.out.println("prefix counter=" + counter);

        Integer beforeDecrease = counter--;
        Integer afterDecrease = --counter;
        System.out.println("before decrease=" + beforeDecrease);
        System.out.println("after decrease=" + afterDecrease);
        System.out.println("counter after decreases=" + counter);

        Integer caller = 10;
        incrementLocally(caller);
        System.out.println("caller=" + caller);

        List<Integer> values = new ArrayList<>(List.of(1, 2));
        for (Integer value : values) {
            value++;
        }
        System.out.println("after local loop=" + values);
        for (int i = 0; i < values.size(); i++) {
            values.set(i, values.get(i) + 1);
        }
        System.out.println("after list update=" + values);

        Integer[] slots = {10};
        Integer oldSlot = slots[0];
        slots[0]++;
        System.out.println("array slot=" + slots[0]);
        System.out.println("old slot alias=" + oldSlot);

        Byte small = 127;
        small++;
        System.out.println("byte overflow=" + small);

        Integer absent = null;
        try {
            absent++;
        } catch (NullPointerException expected) {
            System.out.println("null increment=NullPointerException");
        }
        System.out.println("absent still null=" + (absent == null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ImmutableWrapperUpdateDemo.java
java ImmutableWrapperUpdateDemo
```

Stdout:

```text
postfix previous=1000
postfix counter=1001
alias=1000
previous is alias=true
prefix current=1002
prefix counter=1002
before decrease=1002
after decrease=1000
counter after decreases=1000
caller=10
after local loop=[1, 2]
after list update=[2, 3]
array slot=11
old slot alias=10
byte overflow=-128
null increment=NullPointerException
absent still null=true
```

`previous is alias=true` xuất phát từ việc hai biến nhận cùng giá trị tham chiếu ban đầu, không cần giả định cache wrapper ở giá trị 1000.

`slots[0]++` khác với tăng một biến `for-each`: phần tử mảng tại chỉ số 0 là một biến có thể được gán lại, nên kết quả boxing được lưu vào đúng ô mảng đó. Biến `oldSlot` vẫn giữ wrapper cũ biểu diễn 10.

Phần cập nhật danh sách dùng `ArrayList` và `set`; thao tác được thực hiện qua API danh sách, không trông chờ biến vòng lặp tự ghi ngược vào collection.

## 6. Các giới hạn quan trọng của phép tăng giảm

### 6.1. null không có giá trị nguyên thủy để tăng

`Integer absent = null; absent++;` phải mở hộp nhưng không có đối tượng để lấy giá trị, nên gây `NullPointerException`. Trong ví dụ này phép cập nhật không hoàn tất và biến vẫn bằng `null`.

Cần quyết định rõ chính sách dữ liệu: từ chối thiếu giá trị, khởi tạo giá trị mặc định, hay xử lý trạng thái chưa có số. Không dùng phép tăng wrapper như một cách mặc nhiên biến `null` thành 0.

### 6.2. final chặn việc ghi lại biến

```java
final Integer fixed = 10;
// fixed++; // Lỗi biên dịch nếu bỏ chú thích
```

`++` cần lưu kết quả trở lại biến, nên không dùng được với biến `final`. Tính bất biến của `Integer` và tính không được gán lại của `final` là hai khái niệm khác nhau, dù trong ví dụ này chúng cùng khiến việc “sửa số tại chỗ” không phải mô hình phù hợp.

### 6.3. Không phải mọi đối tượng Number đều dùng được ++

`Integer`, `Long`, `Byte`, `Short`, `Float`, `Double` và `Character` có những phép mở hộp số phù hợp để tham gia toán tử tăng/giảm. `Boolean` không phải giá trị số để tăng.

Một biến có kiểu tĩnh `Number` cũng không tự dùng được `++` chỉ vì đối tượng runtime tình cờ là `Integer`. Cần kiểu của toán hạng đáp ứng quy tắc chuyển sang kiểu số mà toán tử yêu cầu.

Tương tự, một lời gọi trả về `Integer` như `values.get(0)` cung cấp một giá trị, không phải biến phần tử có thể ghi lại bằng toán tử. Không viết `values.get(0)++`; dùng `set` hoặc một API cập nhật rõ ràng.

### 6.4. Wrapper không thay quy tắc tràn số

Trong `Byte small = 127; small++;`, phép tính có chuyển đổi số thích hợp rồi kết quả được thu hẹp về kiểu cần lưu và boxing lại; giá trị kết quả là -128. Wrapper không tạo ra số nguyên có độ lớn tùy ý.

Với `Integer`, tràn theo số học `int` cũng không tự biến thành một giá trị rộng hơn. Với số dấu phẩy động, tăng 1 còn chịu quy tắc làm tròn của kiểu số đó.

Vì có quy tắc lưu trở lại kiểu biến, không được thay mọi `x++` bằng `x = x + 1` rồi cho rằng hai cú pháp luôn có cùng tính hợp lệ. Ví dụ với biến `Byte`, biểu thức cộng thông thường có thể cho kết quả `int` không gán trực tiếp lại `Byte`, trong khi toán tử tăng có quy tắc thu hẹp/boxing riêng.

## 7. Bộ đếm dùng chung là một yêu cầu khác

Tính bất biến của wrapper không làm phép `counter++` trở thành một thao tác nguyên tử. Nó là quá trình đọc, tính và ghi lại; nhiều luồng cùng cập nhật có thể làm mất cập nhật nếu không có giao thức phù hợp. Chỉ thêm `volatile` cho một biến wrapper cũng không biến toàn bộ phép đọc-sửa-ghi thành nguyên tử.

Nếu cần một đối tượng bộ đếm có trạng thái thay đổi và thao tác tăng nguyên tử, các kiểu chuyên dụng như [AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html) có hợp đồng khác: chúng là những đối tượng đếm có thể cập nhật, không phải một wrapper `Integer` bất biến đang được tự động mở/đóng hộp.

Không cần thay mọi biến số bằng kiểu nguyên tử. Chọn `int` cho số cục bộ khi phù hợp, wrapper khi API hoặc mô hình dữ liệu cần kiểu tham chiếu, và cơ chế đồng bộ/bộ đếm chuyên dụng khi yêu cầu chia sẻ giữa luồng thật sự tồn tại.

Thông tin lớp bao `int` được mô tả trong [Integer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html). Khi đọc một biểu thức tăng, hãy tách kiểu đối tượng khỏi hợp đồng cập nhật của biến hoặc API đang dùng.

## 8. Tự kiểm tra

1. `Integer x = 10; x++;` có sửa đối tượng wrapper biểu diễn 10 thành 11 không?
2. Với `Integer y = x; x++;`, biến `y` có tự tăng theo không?
3. Tiền tố và hậu tố khác nhau ở điều gì khi dùng kết quả biểu thức?
4. Vì sao `final Integer x = 10; x++;` không biên dịch?
5. Vì sao `array[0]++` có thể cập nhật ô mảng nhưng `list.get(0)++` không hợp lệ?

Đáp án:

1. Không. Nó mở hộp, tính kết quả, boxing và ghi lại biến `x`.
2. Không. `y` giữ tham chiếu đã được sao chép trước khi `x` được gán lại.
3. Hậu tố cung cấp giá trị trước cập nhật; tiền tố cung cấp giá trị sau cập nhật. Cả hai vẫn ghi kết quả vào biến toán hạng.
4. Phép tăng cần gán lại biến, nhưng biến đó được khai báo không cho gán lại.
5. Phần tử mảng là một biến có thể nhận kết quả lưu lại; giá trị trả về từ lời gọi `get` không phải một vị trí biến có thể ghi bằng toán tử.

Khi thấy một wrapper tăng hoặc giảm, hãy hỏi kết quả được lưu trở lại biến nào. Theo dõi đúng nơi được gán lại sẽ giải thích cả tính bất biến, alias, tham số phương thức và hành vi với collection.
