# Phương thức trợ giúp cho wildcard capture

## 1. Khi biết thao tác an toàn nhưng trình biên dịch vẫn từ chối

Giả sử cần hoán đổi hai phần tử trong một danh sách. Thuật toán chỉ đưa các phần tử vốn thuộc danh sách trở lại chính danh sách đó; nó không tạo thêm giá trị thuộc kiểu khác. Ta muốn API nhận được cả `List<String>`, `List<Integer>` và các kiểu danh sách khác, nên chọn tham số `List<?>`.

Khó khăn xuất hiện khi vừa đọc vừa ghi phần tử. Dấu `?` diễn tả “một kiểu cụ thể chưa được biết tên”, nhưng trong thân phương thức không có tên để khai báo biến giữ kiểu ấy. Nếu biến tạm bị khai báo thành `Object`, thông tin liên hệ giữa phần tử và danh sách bị mất.

**Wildcard capture** là cơ chế trình biên dịch biểu diễn kiểu chưa biết bằng một biến kiểu nội bộ. Một **phương thức trợ giúp (helper method)** generic cho ta đặt tên như `T` cho kiểu đó trong một phạm vi đủ để thực hiện thuật toán.

Kỹ thuật này vẫn áp dụng trong Java hiện nay. Bài dùng ví dụ chạy với JDK 17 trở lên, không cần kiểu thô, ép kiểu không được kiểm tra hoặc tắt cảnh báo.

## 2. Tái hiện lỗi trước khi sửa

### 2.1. List<?> không phải List<Object>

Với `List<?>`, ta có thể đọc một phần tử và nhìn nó như `Object`:

```java
static void inspect(List<?> items) {
    Object value = items.get(0);
    System.out.println(value);
}
```

Đây là khai báo phương thức minh họa, đặt trong một lớp có import `java.util.List`. Nó giả định danh sách có ít nhất một phần tử.

Nhưng không thể tùy ý đưa một `Object` vào danh sách:

```java
static void broken(List<?> items) {
    Object value = items.get(0);
    items.set(0, value); // Loi bien dich
}
```

`items` có thể là `List<String>`. Một biến `Object` nói chung có thể giữ cả số nguyên, chuỗi hoặc đối tượng bất kỳ. Hợp đồng kiểu không bảo đảm mọi giá trị `Object` phù hợp với kiểu phần tử thực tế của danh sách.

Dù ở đây `value` vừa được đọc từ cùng danh sách, kiểu khai báo `Object` không giữ lại mối quan hệ đó để `set` sử dụng.

### 2.2. Viết gọn biểu thức không giải quyết được vấn đề

Đoạn sau cũng không biên dịch:

```java
static void stillBroken(List<?> items) {
    items.set(0, items.get(0));
}
```

Trình biên dịch không xem dấu `?` như một tên kiểu ổn định có thể dùng chung tùy ý giữa mọi lần truy cập. Trong tình huống này, kiểm tra biểu thức không chứng minh được đối số của `set` có đúng kiểu phần tử mà lời gọi yêu cầu.

Thông báo lỗi thường nhắc tới:

```text
capture of ?
CAP#1
incompatible types
```

Đây chỉ là các cụm thường gặp, không phải nguyên văn một thông báo cố định. Cách đánh số `CAP#1`, `CAP#2` và cách trình bày phụ thuộc trình biên dịch, phiên bản và ngữ cảnh.

`CAP#1` không phải lớp bị thiếu, cũng không phải một kiểu mà ta có thể import. Nó là tên nội bộ của trình biên dịch cho một kiểu được bắt giữ.

## 3. Cách sửa: giữ cùng một T bên trong helper

Tách giao diện dễ gọi khỏi phần triển khai cần một tên kiểu:

```java
static void rewriteFirst(List<?> items) {
    rewriteFirstHelper(items);
}

private static <T> void rewriteFirstHelper(List<T> items) {
    T value = items.get(0);
    items.set(0, value);
}
```

Đây là hai phương thức minh họa trong cùng một lớp.

Ba vị trí gắn với nhau:

1. `List<T>` nói rằng danh sách chứa phần tử kiểu `T`.
2. `T value` giữ nguyên kiểu đó khi đọc.
3. `set(0, value)` nhận đúng `T` mà danh sách yêu cầu.

Khi gọi `rewriteFirstHelper(items)` từ tham số `List<?>`, trình biên dịch suy luận `T` tương ứng với kiểu được bắt giữ của đối số trong lời gọi đó. **Nó không chọn `Object` rồi biến danh sách thành `List<Object>`.**

Có thể hình dung:

```text
Ben ngoai:
    List<?>                      kieu phan tu chua duoc dat ten
        |
        | goi helper va suy luan kieu
        v
Ben trong helper:
    List<T> -> get -> T -> set    cung mot T xuyen suot
```

Không có đối tượng bọc mới, không tạo bản sao danh sách và không kiểm tra kiểu phần tử bằng phản chiếu lúc chạy. Đây là cách làm cho mối quan hệ kiểu của thuật toán được thể hiện tại thời điểm biên dịch. Cơ sở ngôn ngữ nằm ở [JLS: Capture Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10).

Đặt helper là `private` giúp API bên ngoài tập trung vào thao tác cần cung cấp. Đây là lựa chọn đóng gói; bản thân capture không yêu cầu từ khóa `private`.

## 4. Ví dụ hoàn chỉnh: hoán đổi, đảo thứ tự và giữ giới hạn Number

Ta cần ba thao tác:

- Hoán đổi hai vị trí trong một danh sách bất kỳ.
- Đảo thứ tự danh sách.
- Với danh sách số, thêm lại phần tử đầu tiên mà vẫn giữ đúng kiểu số gốc.

Các helper chỉ di chuyển hoặc dùng lại phần tử của chính danh sách. Chúng không cố tạo một giá trị mới của kiểu chưa biết.

Lưu chương trình dưới tên `WildcardHelperDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class WildcardHelperDemo {
    public static void swapAny(List<?> values, int first, int second) {
        Objects.requireNonNull(values, "values");
        Objects.checkIndex(first, values.size());
        Objects.checkIndex(second, values.size());
        swapHelper(values, first, second);
    }

    private static <T> void swapHelper(
            List<T> values, int first, int second) {
        T saved = values.get(first);
        values.set(first, values.get(second));
        values.set(second, saved);
    }

    public static void reverseAny(List<?> values) {
        Objects.requireNonNull(values, "values");
        reverseHelper(values);
    }

    private static <T> void reverseHelper(List<T> values) {
        for (int left = 0, right = values.size() - 1;
                left < right; left++, right--) {
            swapHelper(values, left, right);
        }
    }

    public static void repeatFirstNumber(List<? extends Number> values) {
        Objects.requireNonNull(values, "values");
        repeatFirstNumberHelper(values);
    }

    private static <N extends Number> void repeatFirstNumberHelper(
            List<N> values) {
        if (!values.isEmpty()) {
            N first = values.get(0);
            values.add(first);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("red", "green", "blue"));
        List<?> unknownWords = words;
        swapAny(unknownWords, 0, 2);
        System.out.println("words = " + words);

        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4));
        reverseAny(numbers);
        System.out.println("reversed = " + numbers);

        List<Double> decimals =
                new ArrayList<>(List.of(1.5, 2.5));
        repeatFirstNumber(decimals);
        System.out.println("decimals = " + decimals);

        List<Integer> empty = new ArrayList<>();
        repeatFirstNumber(empty);
        System.out.println("empty = " + empty);

        try {
            swapAny(words, 0, 99);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("bad index rejected");
        }
        System.out.println("words after rejection = " + words);

        try {
            swapAny(List.of("left", "right"), 0, 1);
        } catch (UnsupportedOperationException exception) {
            System.out.println("unmodifiable list rejected");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all WildcardHelperDemo.java
java WildcardHelperDemo
```

Stdout:

```text
words = [blue, green, red]
reversed = [4, 3, 2, 1]
decimals = [1.5, 2.5, 1.5]
empty = []
bad index rejected
words after rejection = [blue, green, red]
unmodifiable list rejected
```

### 4.1. Vì sao swapAny nhận List<?> mà vẫn thay đổi được danh sách?

Thuật toán không đưa một `Object` bất kỳ vào danh sách. `swapHelper` lấy hai giá trị thuộc cùng `T` rồi hoán đổi chúng, nên không phá vỡ hợp đồng kiểu phần tử.

`unknownWords` và `words` cùng tham chiếu một đối tượng danh sách. Thay đổi qua helper hiển thị ngay khi in `words`.

`List<?>` không bảo đảm bất biến. Nó giới hạn những gì có thể làm với **kiểu phần tử chưa được đặt tên** tại một vị trí sử dụng; helper tạo phạm vi có tên để diễn đạt một số thao tác an toàn.

### 4.2. Vì sao helper cho Number có thêm giới hạn?

Tham số công khai là `List<? extends Number>`. Helper dùng `<N extends Number>` để giữ thông tin: phần tử vừa có một kiểu thống nhất `N`, vừa thuộc họ `Number`.

Với `List<Double>`, helper dùng lại một giá trị `Double`. Với `List<Integer>`, nó dùng lại một giá trị `Integer`. Việc bắt giữ kiểu không cho phép biến một số thực thành số nguyên hoặc thêm một kiểu số khác tùy ý.

Điều này hợp lệ:

```java
N first = values.get(0);
values.add(first);
```

Điều sau không hợp lệ bên trong helper:

```java
// values.add(Double.valueOf(3.5)); // N co the la Integer
// values.add(Integer.valueOf(3));  // N co the la Double
```

Giới hạn `extends Number` bảo đảm có thể dùng các phương thức của `Number`; nó không có nghĩa `N` chính là `Number`.

Nếu thuật toán chỉ cần di chuyển phần tử mà không cần khả năng riêng của `Number`, helper `<T>` không giới hạn cũng có thể đủ. Giữ giới hạn khi thân helper thực sự cần nó hoặc khi muốn thể hiện rõ hợp đồng nội bộ.

### 4.3. Hợp đồng chỉ số và khả năng sửa vẫn tồn tại

`swapAny` kiểm tra cả hai chỉ số trước khi sửa. Trong trường hợp chỉ số `99` của ví dụ, danh sách được giữ nguyên vì lỗi xảy ra trước lời gọi helper.

Điều đó không biến thao tác thành một giao dịch có cơ chế hoàn tác. Nếu một cài đặt danh sách đặc biệt ném lỗi trong một lần `set` sau khi lần `set` trước đã thành công, helper không tự phục hồi. Ví dụ cũng không hỗ trợ danh sách bị luồng khác thay đổi đồng thời.

Hoán đổi và đảo thứ tự yêu cầu `set` được hỗ trợ. `repeatFirstNumber` yêu cầu `add` khi danh sách có phần tử. Hệ thống generic không chứng minh các thao tác tùy chọn này được cài đặt. Đối tượng do `List.of` tạo ra không cho sửa cấu trúc hay thay phần tử, nên `swapAny` trong chương trình bắt được `UnsupportedOperationException`.

## 5. Helper không chứng minh được hai wildcard độc lập là cùng kiểu

Đây là giới hạn quan trọng nhất của kỹ thuật.

Giả sử có hai danh sách số:

```java
List<? extends Number> left = new ArrayList<Integer>();
List<? extends Number> right = new ArrayList<Double>();
```

Cả hai cùng có giới hạn trên `Number`, nhưng một bên chứa `Integer`, bên kia chứa `Double`. Vì vậy, không thể lấy một phần tử bên phải để đặt vào vị trí bên trái một cách tổng quát.

### 5.1. Bản sửa có vẻ hợp lý nhưng vẫn bị từ chối

Các phương thức sau minh họa lỗi biên dịch:

```java
static void brokenPair(
        List<? extends Number> left,
        List<? extends Number> right) {
    swapFirstHelper(left, right); // Khong suy luan duoc cung mot T
}

private static <T> void swapFirstHelper(
        List<T> left, List<T> right) {
    T saved = left.get(0);
    left.set(0, right.get(0));
    right.set(0, saved);
}
```

Helper yêu cầu hai danh sách có cùng `T`. Phương thức bên ngoài chỉ bảo đảm mỗi danh sách có một kiểu phần tử riêng thuộc họ `Number`; nó không thiết lập quan hệ hai kiểu đó bằng nhau.

Thông báo thường biểu diễn chúng bằng hai biến capture khác nhau. Cùng giới hạn trên không có nghĩa cùng kiểu.

Đây là lỗi của **hợp đồng thiếu quan hệ kiểu**, không phải một thủ thuật cú pháp còn thiếu. Ép cả hai thành `List<Number>` chỉ che giấu vấn đề và có thể đưa `Double` vào `List<Integer>`.

### 5.2. Nếu nghiệp vụ yêu cầu cùng kiểu, công khai quan hệ đó

Có thể thiết kế:

```java
static <T> void swapFirst(List<T> left, List<T> right) {
    T saved = left.get(0);
    left.set(0, right.get(0));
    right.set(0, saved);
}
```

Khi đó:

- Hai đối số `List<Integer>` phù hợp.
- Hai đối số `List<Number>` phù hợp, kể cả khi chúng đang giữ các kiểu con khác nhau.
- `List<Integer>` và `List<Double>` không phù hợp.
- `List<Integer>` và `List<Number>` cũng không phù hợp, vì thao tác trao đổi hai chiều có thể đưa một `Double` từ danh sách `Number` sang danh sách `Integer`.

`T` phải được khai báo ở nơi quan hệ giữa hai danh sách còn được biết. Không thể nhận hai `List<?>` độc lập rồi tự khẳng định chúng cùng kiểu trong thân phương thức.

Các ví dụ `swapFirst` giả định hai danh sách không rỗng, hỗ trợ `set` và không bị thay đổi đồng thời.

### 5.3. Nếu chỉ chuyển một chiều, có thể cần PECS

Nếu yêu cầu thật sự là lấy từ nguồn rồi đưa vào đích, chữ ký phù hợp có thể là:

```java
static <T> void append(
        Iterable<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Nguồn cung cấp `T`, đích tiếp nhận `T`. Không cần giả vờ hai danh sách có cùng kiểu phần tử. Phải xác định đúng yêu cầu: **sắp xếp lại nội bộ**, **trao đổi hai chiều**, và **chuyển một chiều** có hợp đồng kiểu khác nhau.

## 6. Vì sao Object, var và ép kiểu không thay thế được helper?

### 6.1. Dùng Object làm mất quan hệ kiểu

```java
static void brokenSwap(List<?> values, int first, int second) {
    Object saved = values.get(first);
    // values.set(second, saved); // Khong bien dich
}
```

`Object` chỉ nói giá trị thuộc hệ kiểu tham chiếu. Nó không nói “đúng kiểu phần tử của danh sách này”.

Helper giữ thông tin mạnh hơn: `T` trong biến và `T` trong `List<T>` là cùng một kiểu.

### 6.2. var không tạo một tên kiểu generic mới

Đổi biến tạm thành `var` không bảo đảm sửa được lỗi:

```java
static void stillBrokenWithVar(List<?> values) {
    var saved = values.get(0);
    // values.set(0, saved); // Khong bien dich
}
```

Trong ví dụ này, biến cục bộ được suy luận thành `Object`. `var` là suy luận kiểu cho biến cục bộ, không phải cú pháp đặt tên tùy ý cho capture rồi sử dụng tên đó trong chữ ký phương thức.

### 6.3. Không dùng kiểu thô hay @SuppressWarnings để vượt rào

Bỏ tham số kiểu hoặc ép kiểu không được kiểm tra có thể khiến mã biên dịch với cảnh báo, nhưng không cung cấp bằng chứng rằng thuật toán giữ đúng kiểu phần tử.

Mục tiêu của helper là để trình biên dịch kiểm tra được tính an toàn của một thao tác vốn hợp lệ. Nếu chỉ loại bỏ cảnh báo trong khi quan hệ kiểu vẫn chưa được chứng minh, vấn đề chưa được giải quyết.

### 6.4. Không gọi helper với <Object> một cách cưỡng ép

Với `List<?> values`, lời gọi `ClassName.<Object>helper(values)` đòi hỏi đối số phù hợp với `List<Object>`. Danh sách bất kỳ không đáp ứng điều đó.

Cần để suy luận kiểu làm việc trong lời gọi `helper(values)`. Kiểu được suy luận tương ứng với phần tử chưa biết của đối số, không phải một kiểu cha rộng do người viết chọn để “cho dễ”.

## 7. Khi nào nên dùng helper và khi nào không cần?

| Tình huống | Cách tiếp cận |
| --- | --- |
| API nhận danh sách bất kỳ; thuật toán chỉ sắp xếp lại phần tử của chính danh sách | `List<?>` bên ngoài và helper `<T>` bên trong |
| Cần gọi phương thức riêng của một giới hạn, rồi ghi lại giá trị cùng kiểu | Helper có giới hạn, chẳng hạn `<N extends Number>` |
| Cần liên kết danh sách, đối số thay thế và kết quả trả về | Đặt `T` ngay trong chữ ký API |
| Chỉ đọc phần tử như `Object` hoặc chỉ dùng `size`, `isEmpty` | Thường không cần helper |
| Hai wildcard độc lập nhưng thuật toán cần trao đổi phần tử | Thiết kế lại hợp đồng; helper không tự tạo quan hệ |
| Thư viện chuẩn đã có đúng thao tác | Ưu tiên API chuẩn và hiểu hợp đồng của nó |

Trong mã ứng dụng, để hoán đổi hai vị trí hoặc đảo thứ tự danh sách, có thể dùng `Collections.swap` và `Collections.reverse`. API chuẩn nhận `List<?>` và vẫn yêu cầu danh sách hỗ trợ thao tác thay phần tử thích hợp. Ví dụ helper trong bài giúp hiểu cách biểu diễn quan hệ kiểu; không cần tự viết lại thuật toán phổ biến trong mọi dự án. Xem [Collections trong Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html).

Không phải phương thức nhận wildcard nào cũng cần helper. Chỉ thêm lớp triển khai khi một tên kiểu giúp thể hiện quan hệ mà thuật toán thực sự cần.

## 8. Cách phân tích một lỗi capture trong công việc

1. **Đọc kiểu yêu cầu và kiểu đang có.** Nếu `set` cần một kiểu capture nhưng biểu thức chỉ có `Object` hoặc `Number`, xác định thông tin kiểu bị mất ở đâu.
2. **Tìm nguồn gốc của giá trị ghi vào.** Nó có đến từ đúng cùng danh sách hay từ một cấu trúc độc lập?
3. **Xác định quan hệ cần giữ.** Nếu chỉ cần dùng lại phần tử trong cùng cấu trúc, helper `<T>` thường diễn tả được.
4. **Giữ giới hạn cần thiết.** Nếu cần thao tác của `Number`, dùng một biến kiểu có giới hạn phù hợp.
5. **Kiểm tra phản ví dụ.** Thử nghĩ tới `List<Integer>` và `List<Double>`. Nếu thuật toán trộn được chúng theo cách phá hợp đồng, lỗi biên dịch đang ngăn một vấn đề thật.
6. **Kiểm tra hợp đồng lúc chạy.** Danh sách có rỗng không, chỉ số có hợp lệ không, có hỗ trợ `set` hay `add` không?

Đừng bắt đầu bằng việc tìm phép ép kiểu cho hết lỗi. Bắt đầu bằng việc chỉ ra vì sao thao tác phải an toàn với **mọi đối số mà chữ ký hiện tại cho phép**.

## 9. Bài tập tự kiểm tra

### Bài 1: Đặt tên cho kiểu còn thiếu

Hoàn thiện helper để đưa phần tử đầu xuống cuối danh sách không rỗng:

```java
static void moveFirstToEnd(List<?> values) {
    moveFirstToEndHelper(values);
}

private static <T> void moveFirstToEndHelper(List<T> values) {
    T first = values.remove(0);
    values.add(first);
}
```

**Giải thích:** `remove(0)` trả về `T` và `add` nhận lại cùng `T`. Không cần biết `T` là chuỗi hay số nguyên.

Ví dụ này yêu cầu danh sách khác `null`, không rỗng và hỗ trợ cả xóa lẫn thêm. Nếu thêm thất bại sau khi xóa thành công, danh sách đã bị thay đổi; helper generic không tự cung cấp hoàn tác. Đoạn mã là một khai báo minh họa, không phải chương trình độc lập.

### Bài 2: Hai dấu ? có cùng kiểu không?

```java
static void process(List<?> first, List<?> second) {
    // Co the mac dinh coi hai kieu phan tu la giong nhau khong?
}
```

**Đáp án:** không. Một đối số có thể là `List<String>` và đối số còn lại là `List<Integer>`. Nếu cần cùng kiểu, phải thể hiện quan hệ bằng một tham số kiểu dùng chung trong chữ ký thích hợp.

### Bài 3: Helper có thể thêm một Double vào List<? extends Number> không?

Giả sử helper khai báo `<N extends Number>` và nhận `List<N>`.

**Đáp án:** không thể tùy ý thêm `Double` vì `N` có thể là `Integer`. Nó có thể đọc một `N` rồi ghi lại chính giá trị có kiểu `N` đó khi danh sách hỗ trợ thao tác.

### Bài 4: Có bắt buộc công khai helper không?

**Đáp án:** không. Helper thường là `private` để giữ chi tiết triển khai bên trong lớp. Nếu người gọi cần một quan hệ kiểu trong hợp đồng công khai, hãy thiết kế một phương thức generic công khai có ý nghĩa; không mở quyền truy cập chỉ để xử lý lỗi capture.

### Bài 5: List<?> có sửa được không?

**Đáp án:** một số thao tác vẫn sửa được danh sách khi đối tượng hỗ trợ, và helper có thể diễn đạt thêm các thao tác dùng lại phần tử cùng kiểu. `?` không phải cơ chế bất biến. `UnsupportedOperationException` là vấn đề hợp đồng sửa của đối tượng, khác với lỗi capture tại thời điểm biên dịch.

Điểm cần nắm là phạm vi của bằng chứng: helper đặt tên cho **một kiểu chưa biết đã tồn tại** và giữ tên đó xuyên suốt thuật toán; nó không tạo quan hệ mới giữa những kiểu độc lập.
