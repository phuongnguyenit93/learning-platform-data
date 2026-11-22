# Lựa chọn wildcard hay tham số kiểu có tên trong chữ ký API

## 1. Chữ ký API phải biểu đạt mối quan hệ mà phương thức cần giữ

Khi thiết kế một phương thức dùng generic, câu hỏi đầu tiên không phải là “viết `?` hay viết `T` cho đẹp”, mà là: **phương thức cần biết gì về kiểu phần tử, và những vị trí nào phải liên hệ với nhau?**

- Wildcard như `?`, `? extends Number`, `? super Integer` diễn đạt chấp nhận một kiểu chưa biết, có thể kèm cận.
- Tham số kiểu có tên như `T`, `R` cho phép nhắc lại cùng một kiểu ở nhiều vị trí: các tham số, kiểu trả về, kiểu của giá trị trung gian hoặc các ràng buộc.
- Hai cách này có thể xuất hiện cùng nhau. Một chữ ký tốt thường dùng tên kiểu để nối các vị trí cần liên hệ, rồi dùng wildcard ở các ranh giới cần linh hoạt.

Ví dụ:

```java
static <T> void appendAll(List<? extends T> source,
                          List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

`T` liên kết kiểu giá trị đi từ nguồn sang đích. `extends` cho phép đọc nguồn dưới dạng `T`; `super` cho phép ghi `T` vào đích. Không cần buộc hai danh sách có đối số kiểu giống hệt nhau.

Đây là nguyên tắc thiết kế vẫn dùng trong Java hiện đại, chẳng hạn chữ ký [Collections.copy trong Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)). Ví dụ `appendAll` ở đây thêm phần tử vào cuối đích; nó không có cùng hành vi với `Collections.copy`, vốn thay thế các vị trí đã tồn tại ở danh sách đích.

## 2. Khi nào chỉ cần wildcard?

### Không quan tâm kiểu phần tử: dùng `?`

Nếu chỉ đếm, kiểm tra rỗng, duyệt dưới dạng `Object` hoặc ghi nhật ký, không cần đặt tên cho kiểu phần tử:

```java
static int countItems(List<?> values) {
    return values.size();
}
```

Chữ ký sau cũng hợp lệ, nhưng khai báo một tên kiểu mà hợp đồng không dùng để biểu đạt quan hệ nào:

```java
static <T> int countItemsGeneric(List<T> values) {
    return values.size();
}
```

Ở trường hợp này, `List<?>` thường đơn giản hơn. Người dùng API không được thêm lợi ích kiểu nào từ `T` vì kết quả vẫn chỉ là `int`.

Không thay bằng `List<Object>` để “nhận mọi danh sách”. Do tính bất biến của generic, một biến `List<String>` không thể truyền vào tham số `List<Object>`.

### Chỉ cần đọc qua một kiểu cha: dùng `? extends`

```java
static double sum(List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Phương thức nhận được `List<Integer>`, `List<Double>` hoặc `List<Number>`. Nó chỉ cần đọc các phần tử như `Number`; kiểu trả về không phụ thuộc kiểu phần tử nguồn. Đoạn minh họa giả định danh sách và các phần tử khác `null`.

Có thể viết `<T extends Number> double sum(List<T> values)`, nhưng tên `T` chưa đem lại quan hệ hữu ích nào trong hợp đồng này. Wildcard diễn đạt đúng nhu cầu với ít khai báo hơn.

### Cần ghi một kiểu đã cố định: dùng `? super`

```java
static void addDefaultScore(List<? super Integer> scores) {
    scores.add(100);
}
```

Kiểu cần thêm đã được nghiệp vụ quyết định là `Integer`. Không cần một `T` chỉ để thay thế tên `Integer`. Phương thức có thể nhận danh sách `Integer`, `Number` hoặc `Object` có hỗ trợ thêm phần tử.

Các ví dụ trong mục này là những phương thức rời; chúng cần import `java.util.List` khi đặt vào lớp Java.

## 3. Khi nào cần tham số kiểu có tên?

### Kiểu trả về cần gắn với kiểu đầu vào

So sánh hai chữ ký:

```java
static Object firstUnknown(List<?> values) {
    return values.get(0);
}

static <T> T first(List<T> values) {
    return values.get(0);
}
```

Cả hai đều đọc phần tử đầu, nhưng chỉ phương thức thứ hai giữ quan hệ kiểu để nơi gọi có thể viết:

```java
List<String> names = List.of("Lan", "Minh");
String name = first(names);
Object unknown = firstUnknown(names);
```

Nếu đổi `first` thành trả `Object`, nơi gọi phải tự kiểm tra hoặc ép kiểu. Chữ ký generic giữ bằng chứng kiểu từ đầu vào đến đầu ra ngay khi biên dịch.

Một biến thể hợp lệ là `<T> T first(List<? extends T> values)`. Nó cho phép đọc phần tử nguồn như `T` và hỗ trợ chọn `T` rộng hơn kiểu phần tử nguồn khi ngữ cảnh cần. `List<T>` là đủ cho phiên bản cơ bản; không thêm wildcard một cách máy móc nếu sự linh hoạt đó không đem lại ích lợi cho API.

Các ví dụ `first` giả định danh sách có phần tử. Với API công khai, cần quy định rõ trường hợp rỗng: ném ngoại lệ, trả `Optional<T>` theo hợp đồng phù hợp hoặc dùng một thiết kế khác. Wildcard không giải quyết quy tắc nghiệp vụ này.

### Một giá trị cần phù hợp với kiểu phần tử của danh sách

```java
static <T> void append(List<? super T> destination, T value) {
    destination.add(value);
}
```

Ở đây, `T` nối kiểu của `value` với khả năng nhận phần tử của `destination`. Ví dụ một `Integer` có thể đi vào `List<Number>`; một `String` không thể tùy ý đi vào danh sách số.

Nếu viết `append(List<?> destination, Object value)`, hợp đồng không còn biểu đạt rằng kiểu của giá trị phải phù hợp với kiểu phần tử bị che trong danh sách. Vì vậy, lệnh `destination.add(value)` bị từ chối.

### Cần đọc rồi ghi theo cùng kiểu

```java
static <T> void replaceFirst(List<T> values, T replacement) {
    values.set(0, replacement);
}
```

`T` liên kết danh sách và giá trị thay thế. Đây là một hợp đồng rõ ràng hơn việc nhận `List<?>` rồi cố ghi một `Object` vào.

Nếu không có giá trị bên ngoài mà chỉ hoán đổi các phần tử sẵn có trong cùng danh sách, API bên ngoài có thể nhận `List<?>`, rồi dùng phương thức generic trợ giúp ở bên trong để ghi nhận kiểu capture. Chỉ đưa tham số kiểu ra giao diện công khai khi nó giúp mô tả hợp đồng mà nơi gọi cần sử dụng.

## 4. Thường phải phối hợp `T` với wildcard

Một phiên bản sao chép quá chặt là:

```java
static <T> void appendAllStrict(List<T> source, List<T> destination) {
    destination.addAll(source);
}
```

Với hai biến có kiểu `List<Integer>` và `List<Number>`, phiên bản này không gọi được: tính bất biến của `List` buộc `T` ở hai danh sách phải phù hợp chính xác với các đối số kiểu đã khai báo.

Nhưng thao tác sao chép từ số nguyên sang danh sách số là an toàn. Chữ ký phù hợp hơn là:

```java
static <T> void appendAll(List<? extends T> source,
                          List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Với `List<Integer>` làm nguồn và `List<Number>` làm đích, có thể chọn `T` là `Integer`: nguồn cung cấp `Integer`, đích nhận được `Integer`.

Ngược lại, chữ ký `appendAll(List<?> source, List<?> destination)` làm mất quan hệ nguồn–đích. Hai dấu `?` độc lập có thể đại diện cho hai kiểu phần tử hoàn toàn khác nhau; không thể tự do chép phần tử từ một danh sách chuỗi sang danh sách số nguyên.

Cách nhớ **PECS — Producer Extends, Consumer Super** chỉ có ý nghĩa khi xác định vai trò từ góc nhìn phương thức:

- Nguồn cung cấp phần tử cho phương thức: `? extends T`.
- Đích nhận phần tử do phương thức truyền vào: `? super T`.

“Đầu vào của phương thức” không luôn đồng nghĩa với `extends`: danh sách đích vẫn là một tham số đầu vào trong cú pháp Java nhưng đóng vai trò nhận phần tử. Xem nguyên tắc này trong [hướng dẫn wildcard của Oracle](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html).

## 5. Khi API có hai kiểu liên hệ khác nhau

Giả sử API biến đổi danh sách từ phần tử kiểu `T` thành kết quả kiểu `R`. Khi đó cần hai tên kiểu và các cận thích hợp:

```java
static <T, R> List<R> mapValues(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Đoạn minh họa cần import `List`, `ArrayList` và `Function` từ thư viện chuẩn.

Đọc chữ ký theo luồng dữ liệu:

1. `source` cung cấp những giá trị đọc được dưới dạng `T`.
2. `mapper` nhận được một `T`, nên đối số đầu của `Function` dùng `? super T`.
3. `mapper` cung cấp kết quả đọc được dưới dạng `R`, nên đối số thứ hai dùng `? extends R`.
4. Phương thức sở hữu danh sách kết quả `List<R>` và trả nó với quan hệ kiểu rõ ràng.

Ví dụ một hàm nhận `Number` có thể xử lý dữ liệu từ `List<Integer>`; không cần buộc hàm chỉ nhận đúng `Integer`. Mô hình cận tương tự xuất hiện ở [Stream.map trong Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#map(java.util.function.Function)). Bài dùng vòng lặp để quan hệ kiểu dễ quan sát, không yêu cầu học cơ chế Stream.

## 6. Hạn chế wildcard ở kiểu trả về khi nó làm mất thông tin

Một phương thức tạo bản sao có thể trả:

```java
static <T> List<T> copyOfValues(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

Nơi gọi nhận một danh sách có kiểu phần tử rõ ràng:

```java
List<Integer> source = List.of(1, 2);
List<Number> copy = copyOfValues(source);
copy.add(3.5);
```

`copy` là một danh sách mới chứa các tham chiếu phần tử từ nguồn. Thêm `3.5` vào bản sao không thêm nó vào danh sách số nguyên gốc.

Nếu thay kết quả thành `List<?>` hoặc `List<? extends T>`, người dùng API phải xử lý một kiểu phần tử chưa biết và có thể không thêm được giá trị họ cần. Khi phương thức có đủ thông tin để trả `List<T>`, giữ thông tin đó thường giúp nơi gọi dễ sử dụng hơn.

Đây là hướng dẫn thiết kế, không phải lệnh cấm mọi wildcard trong kiểu trả về. Có những API cần biểu đạt kiểu chưa biết thực sự. Hãy giữ wildcard khi đó là hợp đồng có chủ đích, thay vì vô tình chuyển khó khăn về quan hệ kiểu sang người dùng.

Ngoài ra, trả `List<? extends T>` không tự bảo đảm danh sách bất biến. Nếu muốn kết quả không cho sửa, phải chọn đối tượng trả về và tài liệu hóa hành vi tương ứng; đó là quyết định khác với chọn cận generic.

## 7. Chương trình hoàn chỉnh để kiểm tra hợp đồng

Lưu mã vào `ApiSignatureDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class ApiSignatureDemo {
    static int countItems(List<?> values) {
        return values.size();
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("List must be nonempty");
        }
        return values.get(0);
    }

    static <T> void appendAll(List<? extends T> source,
                              List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static <T, R> List<R> mapValues(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    static <T> List<T> copyOfValues(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        String name = first(names);
        System.out.println("count = " + countItems(names));
        System.out.println("first = " + name);

        List<Integer> integers = List.of(1, 2);
        List<Number> numbers = new ArrayList<>();
        numbers.add(0.5);
        appendAll(integers, numbers);
        System.out.println("numbers = " + numbers);

        Function<Number, String> label = n -> "value=" + n.intValue();
        List<String> labels = mapValues(integers, label);
        System.out.println("labels = " + labels);

        List<Number> copy = copyOfValues(integers);
        copy.add(3.5);
        System.out.println("copy = " + copy);
        System.out.println("source = " + integers);

        // Integer wrong = first(names); // Không phù hợp quan hệ kiểu.
        // appendAll(names, numbers);    // Không thể ghi String vào List<Number>.
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ApiSignatureDemo.java
java ApiSignatureDemo
```

Kết quả chuẩn:

```text
count = 2
first = Lan
numbers = [0.5, 1, 2]
labels = [value=1, value=2]
copy = [1, 2, 3.5]
source = [1, 2]
```

Các dòng chú thích ở cuối `main` là ví dụ bị từ chối khi biên dịch. Chúng không được bật trong chương trình chạy phía trên.

`appendAll` giả định nguồn và đích là những danh sách riêng, không bị sửa đồng thời. `destination` phải hỗ trợ thêm phần tử. Chữ ký generic chỉ bảo đảm tương thích kiểu; hợp đồng vẫn cần nêu rõ yêu cầu về khả năng sửa, `null`, tác động lên dữ liệu và các trường hợp biên.

## 8. Những quy tắc dễ áp dụng sai

### “`T` xuất hiện một lần thì luôn thay bằng `?`”

Đây chỉ là gợi ý rà soát. Cần đọc cả thân phương thức và ràng buộc, không chỉ đếm chữ `T`. Một tên kiểu có thể cần cho biến trung gian hoặc cho một ràng buộc phức tạp. Ngược lại, việc lặp lại `T` nhiều lần không tự chứng minh hợp đồng đó đã đúng nhu cầu nghiệp vụ.

### “Một `T` có nghĩa mọi đối tượng phải cùng lớp lúc chạy”

Không. Kiểu suy luận có thể là kiểu cha chung. Ví dụ `<T> void inspectPair(T a, T b)` có thể được gọi với một chuỗi và một số khi các ràng buộc cho phép chọn kiểu chung. `T` biểu đạt quan hệ tương thích tĩnh, không phải kiểm tra `a.getClass() == b.getClass()`.

Riêng với hai tham số `List<T>`, tính bất biến của `List` tạo ràng buộc chặt hơn so với hai tham số giá trị `T` riêng lẻ. Cần phân biệt hai cấu trúc chữ ký này.

### “`extends` là chỉ đọc, `super` là chỉ ghi”

Đó là cách nhớ vai trò, không phải mô tả tuyệt đối. Có thể đọc từ `List<? super Integer>` như `Object`; `List<? extends Number>` vẫn có những thao tác thay đổi được hệ thống kiểu chấp nhận, chẳng hạn `clear()`. Đừng dùng wildcard để hứa dữ liệu không thể thay đổi.

### “Càng nhiều wildcard thì API càng tốt”

Wildcard có cận giúp linh hoạt đúng chỗ, nhưng cũng tăng độ khó đọc. Bắt đầu từ quan hệ dữ liệu cần có, sau đó mở các vị trí nguồn/đích khi lợi ích rõ ràng. Không làm mất tên kiểu cần liên kết đầu ra, cũng không buộc mọi tham số vào cùng `T` nếu chúng độc lập.

### “Có thể cung cấp hai overload chỉ khác `List<T>` và `List<?>`”

Không thể dựa vào khác biệt đó để tạo overload cùng tên, cùng cấu trúc tham số. Sau xóa kiểu, cả hai đều có dạng nhận `List`, dẫn tới xung đột khai báo. Các phiên bản so sánh trong bài dùng tên khác nhau hoặc là phương án thay thế, không phải tất cả cùng tồn tại dưới một tên trong một lớp.

## 9. Bảng chọn nhanh theo nhu cầu

| Nhu cầu của phương thức | Chữ ký gợi ý |
| --- | --- |
| Chỉ đếm hoặc duyệt như `Object` | `int count(List<?> values)` |
| Chỉ đọc các phần tử như `Number` | `double sum(List<? extends Number> values)` |
| Ghi `Integer` do nghiệp vụ quyết định | `void addScore(List<? super Integer> values)` |
| Trả phần tử giữ liên hệ với đầu vào | `<T> T first(List<T> values)` |
| Ghi một giá trị với kiểu do nơi gọi quyết định | `<T> void append(List<? super T> values, T value)` |
| Chuyển giá trị từ nguồn sang đích tương thích | `<T> void appendAll(List<? extends T> src, List<? super T> dst)` |
| Biến đổi kiểu đầu vào thành kiểu đầu ra | `<T, R> List<R> mapValues(List<? extends T> src, Function<? super T, ? extends R> fn)` |

Hãy đọc bảng theo hợp đồng cần giữ, không dùng nó như công thức thay thế cho việc hiểu thuật toán. Wildcard diễn đạt sự linh hoạt của một vị trí kiểu; tham số kiểu có tên nối các vị trí cần liên hệ với nhau.
