# Hạn chế wildcard ở kiểu trả về khi làm API khó sử dụng

## 1. Một API dễ gọi nhưng có thể khó dùng kết quả

Giả sử phương thức trả một danh sách số:

```java
static List<? extends Number> loadNumbers() {
    return new ArrayList<Integer>(List.of(1, 2));
}
```

Nơi gọi nhận được một danh sách có kiểu phần tử nào đó là `Number` hoặc kiểu con của `Number`. Đọc dưới dạng `Number` là an toàn:

```java
List<? extends Number> values = loadNumbers();
Number first = values.get(0);
```

Nhưng nơi gọi không biết tên kiểu phần tử cụ thể. Một số thao tác có vẻ tự nhiên lại bị từ chối:

```java
// List<Number> numbers = loadNumbers(); // Không gán được.
// values.add(3.5);                     // Không biết kiểu phần tử để thêm.
// values.set(0, 100);                  // Cũng thiếu bằng chứng tương thích.
```

Wildcard không làm phương thức sai. Vấn đề thiết kế là: **API có chủ đích trả một kiểu phần tử chưa biết, hay vô tình làm mất thông tin mà nó có thể cung cấp rõ hơn?**

Nếu những người dùng API liên tục phải tạo bản sao, viết hàm capture hoặc ép kiểu chỉ để tiếp tục công việc thường ngày, nên xem lại hợp đồng trả về.

[Hướng dẫn wildcard của Oracle](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html) khuyên tránh dùng wildcard ở kiểu trả về khi nó buộc người gọi phải xử lý thêm wildcard. Đây là hướng dẫn thiết kế cần áp dụng theo ngữ cảnh, không phải lệnh cấm tuyệt đối.

## 2. `? extends Number` không phải `Number`

Cần phân biệt:

- `List<Number>`: kiểu phần tử của danh sách được khai báo là `Number`.
- `List<? extends Number>`: danh sách có một kiểu phần tử chưa biết, với cận trên `Number`.

Một giá trị kiểu `List<Integer>` dùng được như `List<? extends Number>`, nhưng không dùng được như `List<Number>`. Nếu có thể coi cùng danh sách số nguyên là `List<Number>`, nơi gọi có thể thêm một `Double` và phá vỡ giả định của những đoạn mã vẫn giữ nó như `List<Integer>`.

Vì thế, không thể sửa chữ ký bằng cách chỉ đổi tên kiểu trả về rồi giữ nguyên một phép trả tham chiếu không tương thích:

```java
static List<Number> numberCopy(List<Integer> source) {
    // return source; // Lỗi biên dịch vì tính bất biến của List.
    return new ArrayList<>(source);
}
```

Ở đây, một danh sách mới được tạo với kiểu phần tử `Number`. Các số nguyên ban đầu phù hợp với kiểu đó, và thêm một `Double` vào bản sao không ghi số thực vào danh sách số nguyên gốc.

Tạo bản sao có chi phí và thay đổi quan hệ chia sẻ dữ liệu. Chỉ làm khi phù hợp với hợp đồng API; không coi nó là thao tác bắt buộc cho mọi kết quả wildcard.

## 3. Chọn kiểu trả về theo điều API thực sự biết

### Biết phần tử là một kiểu cụ thể

Nếu nghiệp vụ tạo điểm số nguyên, kiểu trả về `List<Integer>` có thể là hợp đồng rõ ràng:

```java
static List<Integer> integerScores() {
    return new ArrayList<>(List.of(10, 20));
}
```

Nơi gọi có thể đọc `Integer`, truyền tiếp cho API nhận danh sách số nguyên và thêm số nguyên nếu đối tượng trả về hỗ trợ thao tác đó.

Không cần dùng `List<? extends Integer>` chỉ để che lớp triển khai `ArrayList`. Kiểu interface `List<Integer>` đã che chi tiết lớp triển khai; wildcard đang che kiểu phần tử, là một quyết định khác.

### Biết danh sách được thiết kế chứa các `Number`

Nếu hợp đồng cho phép nhiều loại số trong cùng danh sách, có thể trả `List<Number>` và tạo dữ liệu phù hợp với hợp đồng đó. Đừng chọn kiểu rộng chỉ vì muốn tránh một lỗi gán: cần xác định rõ nơi gọi có được bổ sung các dạng `Number` khác hay không.

### Kiểu phần tử được liên kết với đầu vào

Dùng tham số kiểu có tên để giữ mối quan hệ:

```java
static <T> List<T> mutableCopy(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

Wildcard ở đầu vào giúp chấp nhận các nguồn phù hợp; `T` ở đầu ra cho người gọi một danh sách với kiểu phần tử có tên rõ ràng.

Ví dụ:

```java
List<Integer> source = List.of(1, 2);
List<Integer> sameElementType = mutableCopy(source);
List<Number> widenedElementType = mutableCopy(source);
```

Trong trường hợp thứ hai, ngữ cảnh đích cho phép suy luận `T` là `Number`, còn nguồn cung cấp `Integer`. Đây là một danh sách mới có kiểu phần tử được chọn phù hợp, không phải đổi nhãn cùng đối tượng danh sách gốc.

## 4. Đừng dùng wildcard để giả làm kết quả không cho sửa

Một hiểu nhầm phổ biến là trả `List<? extends T>` để tạo một “danh sách chỉ đọc”. Wildcard hạn chế thao tác truyền một phần tử có kiểu chưa biết; nó không loại bỏ mọi phương thức thay đổi danh sách.

Với một đối tượng `ArrayList`:

```java
List<? extends Number> values = loadNumbers();
values.clear(); // Hợp lệ về kiểu và thực sự làm rỗng ArrayList ở ví dụ.
```

Nơi gọi còn có thể xóa phần tử theo chỉ số hoặc thực hiện những thao tác khác có chữ ký không yêu cầu cung cấp đúng kiểu phần tử bị che.

Nếu mục đích là trả một ảnh chụp trạng thái (snapshot) không cho sửa, có thể giữ kiểu phần tử rõ ràng và chọn đối tượng phù hợp:

```java
static <T> List<T> snapshot(Collection<? extends T> source) {
    return List.copyOf(source);
}
```

Ở đây:

- Chữ ký `List<T>` giữ thông tin kiểu.
- Đối tượng do `List.copyOf` cung cấp không hỗ trợ thêm, xóa hoặc thay thế phần tử.
- Thay đổi cấu trúc collection nguồn sau đó không làm cấu trúc kết quả thay đổi theo.
- Không chấp nhận phần tử `null`.
- Các đối tượng phần tử được chia sẻ; đây không phải sao chép sâu.

Nếu phần tử là `StringBuilder`, việc sửa cùng `StringBuilder` qua tham chiếu khác vẫn được nhìn thấy trong danh sách kết quả. Không cho sửa danh sách và làm mọi đối tượng phần tử bất biến là hai cam kết khác nhau.

Đọc các đặc điểm cụ thể trong [List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)). Không dựa vào số lượng đối tượng được cấp phát hoặc giả định `copyOf` luôn tạo một instance mới; điều cần dựa vào là hợp đồng của kết quả.

## 5. Wildcard đầu vào và đầu ra có tác động khác nhau

Ở đầu vào:

```text
<T> List<T> mutableCopy(Collection<? extends T> source)
```

`? extends T` giúp phương thức nhận nguồn linh hoạt, còn việc xử lý kiểu chưa biết nằm trong triển khai của phương thức. Phương thức có thể đọc từng phần tử như `T` và xây kết quả `List<T>`.

Nếu đổi đầu ra thành `List<? extends T>`, phần khó khăn đó xuất hiện lại ở nơi gọi:

```java
static <T> List<? extends T> unclearCopy(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

Triển khai này đã tạo được một danh sách phù hợp để trả `List<T>`, nhưng chữ ký lại che kiểu phần tử đi. Nơi gọi không còn gán trực tiếp vào `List<T>` tương ứng hoặc truyền mọi giá trị `T` vào thao tác nhận phần tử.

Cần hỏi: wildcard đầu ra đang bảo vệ một hợp đồng có chủ đích hay chỉ làm thông tin về kiểu kém rõ ràng? Trong ví dụ sao chép, giữ `List<T>` thường hữu ích hơn.

PECS là cách nghĩ về vai trò cung cấp/nhận phần tử ở các tham số. Nó không dẫn tới quy tắc rằng mọi phương thức trả collection đều phải dùng `? extends`.

## 6. Không hứa một `T` tùy ý mà không có bằng chứng

Tránh sửa mọi wildcard bằng một tham số kiểu chỉ xuất hiện ở kết quả rồi cho rằng nơi gọi muốn kiểu nào cũng được:

```text
<T> List<T> loadScores()
```

Nếu dữ liệu thực luôn là các số nguyên đã có, chữ ký này không tạo ra bằng chứng rằng chúng có thể là những chuỗi do nơi gọi yêu cầu. Một triển khai không được cast unchecked dữ liệu sẵn có thành `List<T>` chỉ để làm chữ ký biên dịch.

Tham số kiểu có tên phải gắn với hợp đồng có thể thực hiện an toàn: dữ liệu đầu vào, một token kiểu được kiểm tra, trạng thái generic của đối tượng hoặc một cách tạo giá trị phù hợp.

Không phải mọi tham số kiểu chỉ xuất hiện ở đầu ra đều sai. Chẳng hạn một hàm tạo danh sách rỗng có thể an toàn cho nhiều `T` vì không có phần tử cần giả định. Cần đánh giá dữ liệu và hành vi thực, không chỉ đếm số lần xuất hiện của tên kiểu.

## 7. `var`, cast và bản sao không có cùng ý nghĩa

### `var` không khôi phục kiểu phần tử bị che

```java
var values = loadNumbers();
// values.add(3.5); // Vẫn lỗi biên dịch.
```

`var` suy luận từ kiểu trả về của lời gọi, không nhìn vào thân `loadNumbers()` để quyết định rằng kết quả hiện được triển khai bằng `ArrayList<Integer>`.

### Ép kiểu không chứng minh dữ liệu phù hợp

Cast từ `List<? extends Number>` thành `List<Number>` có thể dẫn tới cảnh báo unchecked và cho nơi gọi quyền ghi vượt hợp đồng của danh sách gốc. Không nên dùng nó để che một vấn đề thiết kế API.

### Bản sao có kiểu rõ ràng tạo một đối tượng chứa mới

```java
List<? extends Number> unknownNumbers = loadNumbers();
List<Number> editable = new ArrayList<>(unknownNumbers);
editable.add(3.5);
```

Đây là thao tác hợp lệ: từng giá trị nguồn đọc được như `Number`, rồi được đặt vào danh sách mới có kiểu phần tử `Number`. Nó không chứng minh rằng đối tượng nguồn vốn đã là `List<Number>`.

Nếu mục đích chỉ là đọc, chưa chắc cần bản sao. Một hàm tiêu thụ phù hợp như `sum(List<? extends Number>)` có thể nhận trực tiếp kết quả wildcard. Nếu kiểm soát API tiêu thụ và nó đang buộc `List<Number>` quá chặt cho nhu cầu chỉ đọc, có thể cần sửa tham số của nó thay vì ép kiểu kết quả.

## 8. Chương trình hoàn chỉnh

Lưu vào `ReturnWildcardDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ReturnWildcardDemo {
    static List<? extends Number> vagueNumbers() {
        return new ArrayList<Integer>(List.of(1, 2));
    }

    static <T> List<T> mutableCopy(Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T> List<T> snapshot(Collection<? extends T> source) {
        return List.copyOf(source);
    }

    static Class<?> runtimeType(Object value) {
        return value.getClass();
    }

    public static void main(String[] args) {
        List<? extends Number> vague = vagueNumbers();
        Number first = vague.get(0);
        System.out.println("first = " + first);

        List<Number> widened = mutableCopy(vague);
        widened.add(3.5);
        System.out.println("widened copy = " + widened);
        System.out.println("original before clear = " + vague);
        vague.clear();
        System.out.println("original after clear = " + vague);

        List<Integer> source = new ArrayList<>(List.of(10, 20));
        List<Integer> precise = mutableCopy(source);
        precise.add(30);
        System.out.println("precise copy = " + precise);
        System.out.println("source = " + source);

        List<Integer> fixed = snapshot(source);
        source.add(99);
        System.out.println("snapshot = " + fixed);
        System.out.println("changed source = " + source);
        try {
            fixed.add(40);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot rejects add");
        }

        StringBuilder text = new StringBuilder("A");
        List<StringBuilder> shallow = snapshot(List.of(text));
        text.append("B");
        System.out.println("shared element = " + shallow);
        System.out.println("runtime type = " + runtimeType(42).getName());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked -encoding UTF-8 ReturnWildcardDemo.java
java ReturnWildcardDemo
```

Kết quả chuẩn:

```text
first = 1
widened copy = [1, 2, 3.5]
original before clear = [1, 2]
original after clear = []
precise copy = [10, 20, 30]
source = [10, 20]
snapshot = [10, 20]
changed source = [10, 20, 99]
snapshot rejects add
shared element = [AB]
runtime type = java.lang.Integer
```

Những điều cần quan sát:

- `vague` đọc được như `Number`, nhưng không nhận một `Double` tùy ý qua thao tác `add`.
- Bản sao `List<Number>` cho phép thêm số thực mà không thêm nó vào danh sách số nguyên gốc.
- `clear()` vẫn làm thay đổi danh sách trả về dưới dạng wildcard.
- Kết quả `List<Integer>` rõ kiểu có thể là bản sao cho sửa hoặc snapshot không cho sửa, tùy đối tượng trả về.
- Snapshot không theo thay đổi cấu trúc nguồn, nhưng vẫn chia sẻ cùng đối tượng phần tử `StringBuilder`.
- `Class<?>` có thể là một kết quả wildcard hợp lý khi bản chất lớp thực tế chưa được biết cụ thể trong hợp đồng.

## 9. Khi wildcard ở kiểu trả về vẫn có ý nghĩa

Không phải API nào cũng có một kiểu phần tử cụ thể cần phơi bày. Một ví dụ là trả token lớp của một đối tượng nhận dưới dạng `Object`:

```java
static Class<?> runtimeType(Object value) {
    return value.getClass();
}
```

Hợp đồng không biết trước giá trị là `Integer`, `String` hay một lớp khác. `Class<?>` biểu đạt đúng điều chưa biết đó. Không nên thay bằng `<T> Class<T>` một cách tùy ý để người gọi chọn một lớp không phù hợp.

Thư viện chuẩn cũng dùng wildcard có chủ đích; [Object.getClass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#getClass()) trả đối tượng lớp với quy tắc kiểu được đặc tả riêng.

Một API làm việc với dữ liệu không đồng nhất hoặc một giao diện trừu tượng cần giữ kiểu tồn tại chưa biết cũng có thể cần wildcard. Điều cần làm là kiểm tra cách người gọi dùng kết quả: nếu họ chỉ cần các thao tác được bảo đảm, wildcard có thể chính xác; nếu họ cần liên tục tự giải quyết capture mà API đã có đủ thông tin để tránh, nên sửa hợp đồng.

## 10. Rà soát một API trả wildcard

Có thể đi theo trình tự:

1. Xác định kiểu phần tử có thực sự chưa biết hay đã được nghiệp vụ/đầu vào xác định.
2. Viết vài lời gọi điển hình: gán biến, đọc phần tử, truyền sang hàm khác và các thao tác sửa được cho phép.
3. Nếu kiểu đã biết, cân nhắc trả `List<Element>` hoặc giữ quan hệ bằng `<T> List<T>`.
4. Xác định riêng quyền sửa, quan hệ chia sẻ dữ liệu, ảnh chụp trạng thái hay khung nhìn (view), quy tắc `null` và chi phí sao chép.
5. Chỉ giữ wildcard khi nó là phần cần thiết của hợp đồng; không bắt nơi gọi cast để thực hiện một tác vụ mà API hứa hỗ trợ.

Với API đang tồn tại, thay đổi kiểu trả về có thể ảnh hưởng mã nguồn của lớp triển khai, phương thức ghi đè (override) và người dùng. Cần kiểm tra các nơi sử dụng thực tế; không đổi `List<? extends X>` thành `List<X>` một cách cơ học rồi giả định mọi tham chiếu trả về đều phù hợp.

## 11. Tự kiểm tra

**Câu 1.** Một phương thức trả `List<? extends Number>` có bảo đảm người gọi không thể thay đổi danh sách không?

Không. Wildcard giới hạn việc cung cấp phần tử có kiểu chưa biết; các thao tác như `clear()` vẫn hợp lệ về kiểu, và có thể thực hiện nếu đối tượng hỗ trợ.

**Câu 2.** Nếu hàm sao chép đọc được nguồn dưới dạng `T` và tự tạo danh sách mới, vì sao thường nên trả `List<T>`?

Vì nó giữ thông tin kiểu mà phương thức đã đủ khả năng bảo đảm, giúp nơi gọi tiếp tục sử dụng kết quả mà không phải xử lý một kiểu phần tử chưa biết mới.

**Câu 3.** Có thể sửa `List<? extends Number>` thành `List<Number>` bằng cách trả trực tiếp cùng một biến `List<Integer>` không?

Không. Tính bất biến của generic ngăn phép gán đó. Cần chọn hợp đồng phù hợp hoặc tạo cấu trúc chứa mới nếu việc sao chép đúng với thiết kế.

**Câu 4.** `List.copyOf` có làm các đối tượng phần tử bất biến sâu không?

Không. Nó bảo đảm danh sách không cho sửa theo hợp đồng, nhưng những đối tượng phần tử có thể vẫn thay đổi qua tham chiếu khác.

**Câu 5.** Có nên loại bỏ mọi wildcard ở kiểu trả về không?

Không. Hãy loại bỏ những wildcard làm mất thông tin hoặc gây khó khăn không cần thiết. Giữ wildcard khi kiểu chưa biết là một phần chính xác, có chủ đích của hợp đồng.
