# Mỗi wildcard `?` có thể đại diện cho một kiểu khác nhau trong Java Generics

Trong Java Generics, dấu hỏi `?` biểu thị **một kiểu tham số chưa xác định**. Khi khai báo `List<?>`, ta biết đó là danh sách thuộc **một kiểu phần tử cụ thể nào đó**, nhưng không biết kiểu ấy là `String`, `Integer` hay một kiểu tham chiếu khác.

Điểm then chốt: **hai vị trí wildcard không mặc nhiên cùng đại diện cho một kiểu**. Mỗi wildcard có thể được trình biên dịch xử lý như một kiểu ẩn riêng. Hai kiểu ẩn đó *có thể trùng nhau trong thực tế*, nhưng nếu chương trình không biểu diễn được quan hệ giữa chúng, trình biên dịch **không được phép giả định chúng bằng nhau**.

Bài học này nằm trong chủ đề *wildcard không giới hạn (unbounded wildcard)* và tập trung vào cách đọc dữ liệu, lý do thao tác chuyển phần tử giữa hai danh sách `List<?>` bị từ chối, cơ chế **wildcard capture**, và cách dùng generic method để giữ an toàn kiểu.

## 1. `List<?>` thực sự nói điều gì?

Xét:

```java
List<String> names = List.of("An", "Binh");
List<Integer> ages = List.of(20, 25);

List<?> first = names;
List<?> second = ages;
```

Cả hai phép gán đều hợp lệ. Khác với `List<Object>`, `List<?>` không khẳng định danh sách chứa `Object`; nó chỉ nói rằng **kiểu đối số hiện chưa được biết**.

- Với `first`, kiểu phần tử thực của danh sách đang được tham chiếu là `String`.
- Với `second`, kiểu phần tử thực là `Integer`.
- Khi chỉ nhìn chữ ký `List<?>`, trình biên dịch không biết rõ từng kiểu ẩn đó.
- Hai dấu `?` **không phải hai biến cùng tên** để ràng buộc chúng với nhau. Chúng có thể biểu thị hai kiểu độc lập.

Một danh sách bất kỳ có thể được đọc qua `List<?>` ở dạng `Object`:

```java
Object name = first.get(0);
Object age = second.get(0);
```

Điều này an toàn vì mọi đối tượng Java thuộc một kiểu tham chiếu đều có thể được sử dụng như `Object`. Nhưng gán trực tiếp `String text = first.get(0)` sẽ không biên dịch, mặc dù người lập trình biết `first` vừa được gán từ `names`: biểu thức `first.get(0)` được kiểm tra theo **kiểu khai báo của `first` là `List<?>`**.

> Hãy hiểu `?` là “có một kiểu phần tử, nhưng người dùng tham chiếu này chưa biết kiểu đó”; đừng hiểu là “mọi phần tử có thể có kiểu bất kỳ và được tự do thêm vào”.

`List<?>` tương đương về ý nghĩa giới hạn kiểu với `List<? extends Object>`. Đây là wildcard **không có ràng buộc tường minh**, có giới hạn trên mặc định là `Object`.

## 2. Hai wildcard độc lập: cùng ký hiệu, chưa chắc cùng kiểu

Phương thức sau nhận **hai danh sách bất kỳ**:

```java
static void showFirstPair(List<?> left, List<?> right) {
    Object a = left.get(0);
    Object b = right.get(0);
    System.out.println(a + " | " + b);
}
```

Chữ ký có hai dấu `?` khác nhau:

```text
showFirstPair(List<?>, List<?>)
                   ^        ^
                kiểu X    kiểu Y
```

Đây là sơ đồ minh họa về **hai kiểu chưa biết**; `X` và `Y` không phải tên kiểu thật trong khai báo. `X` và `Y` *có thể bằng nhau hoặc khác nhau*, nhưng chữ ký không đòi hỏi chúng bằng nhau.

Ví dụ cả hai lời gọi đều hợp lệ (giả sử đã khai báo phương thức và danh sách):

```java
showFirstPair(List.of(10, 20), List.of("An", "Binh"));
showFirstPair(List.of("Java"), List.of("Generics"));
```

Ở lời gọi đầu, các danh sách mang phần tử thuộc hai kiểu khác nhau. Ở lời gọi sau, cả hai danh sách đều có phần tử `String`. **Chữ ký `List<?>` chấp nhận cả hai trường hợp**, vì nó không ràng buộc hai đối số kiểu với nhau.

Điểm quan trọng hơn: kể cả khi hai tham chiếu thực tế trỏ vào **cùng một đối tượng danh sách**, quan hệ đó cũng không được suy ra thành một ràng buộc kiểu chung giữa hai lần dùng `?`.

```java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<?> a = original;
List<?> b = original;

Object x = a.get(0); // Hợp lệ.
Object y = b.get(0); // Hợp lệ.
a.set(0, b.get(0));  // LỖI BIÊN DỊCH.
```

Dòng `set` cố tình minh họa lỗi, không phải mã chạy độc lập. Trong hoàn cảnh này, con người thấy `a` và `b` cùng trỏ tới `original`, nhưng kiểu tĩnh `List<?>` không cung cấp bằng chứng về việc kiểu capture dùng cho tham số ghi của `a` bằng kiểu phần tử đọc từ `b`.

## 3. Vì sao không thể chuyển phần tử giữa hai `List<?>`?

Thử viết phương thức:

```java
static void moveFirst(List<?> destination, List<?> source) {
    destination.add(source.get(0)); // LỖI BIÊN DỊCH.
}
```

Giả sử hai dấu `?` luôn được coi là cùng kiểu thì lệnh `add` sẽ có vẻ hợp lệ. Nhưng phương thức này cũng có thể được gọi với:

```java
List<Integer> destination = new ArrayList<>(List.of(1));
List<String> source = List.of("Java");

// moveFirst(destination, source);
// Nếu phương thức sai ở trên được chấp nhận, nó có thể
// đưa String vào danh sách chỉ dành cho Integer.
```

Hợp đồng `List<Integer>` yêu cầu phần tử thêm vào tương thích với `Integer`. `source.get(0)` từ `List<String>` trả về `String`. Do đó Java cấm phép ghi ngay ở thời điểm biên dịch.

Ta có thể tóm tắt nguyên tắc như sau:

| Thao tác với hai `List<?>` | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `Object a = left.get(0)` | Có | Mọi kiểu phần tử đều đọc được dưới dạng `Object` |
| `Object b = right.get(0)` | Có | Tương tự cho wildcard thứ hai |
| `left.add(right.get(0))` | Không | Chưa biết kiểu của `right` có phù hợp với `left` |
| `left.set(0, right.get(0))` | Không | Đổi phần tử cũng phải thỏa kiểu phần tử của `left` |
| `left.add(null)` | Có về mặt kiểu | `null` tương thích mọi kiểu tham chiếu; collection vẫn có thể từ chối runtime |
| `left.clear()` | Có về mặt kiểu | Xóa phần tử không đưa vào kiểu mới; collection vẫn có thể không hỗ trợ |
| `left.contains(right.get(0))` | Có về mặt kiểu | `contains(Object)` nhận `Object` để kiểm tra, không thêm phần tử |

Không được dùng `?` như cách lách quy tắc an toàn kiểu. Dấu `?` cho phép **quan sát dữ liệu chung**, đồng thời giới hạn các thao tác yêu cầu phải biết kiểu phần tử.

## 4. Wildcard capture: trình biên dịch gắn một kiểu ẩn vào `?`

Khi cần xử lý `List<?>`, trình biên dịch có thể thực hiện **capture conversion**: tạm thời xem wildcard như một kiểu chưa biết nhưng nhất quán trong phạm vi thích hợp. Thông báo lỗi của `javac` đôi khi nhắc đến `capture#1 of ?`, `capture#2 of ?`.

Ví dụ mang tính minh họa, không phải mã Java cần khai báo:

```text
List<?> left  → List<CAP#1>
List<?> right → List<CAP#2>

CAP#1 và CAP#2:
- Đều có giới hạn trên tương thích Object.
- Không có ràng buộc rằng CAP#1 = CAP#2.
- Có thể trùng kiểu cụ thể tại runtime; trình biên dịch vẫn không được giả định.
```

Các tên `CAP#1` và `CAP#2` chỉ mô tả cách hiểu lỗi, **không phải kiểu Java có thể viết trong mã nguồn**. Số thứ tự và lời báo lỗi cụ thể do trình biên dịch quyết định, không phải một phần của API.

Một ví dụ đặc biệt dễ nhầm:

```java
static <T> void requireSameType(List<T> one, List<T> two) {
    // Chữ ký yêu cầu cùng một T cho cả hai tham số.
}

static void demo(List<?> items) {
    requireSameType(items, items); // LỖI BIÊN DỊCH.
}
```

Dù lặp **chính cùng biến** `items` hai lần, hai biểu thức đối số có thể được capture độc lập. Trình biên dịch không suy ra được một `T` chung thỏa cả hai ràng buộc bằng nhau.

Điều này không mâu thuẫn với việc truyền **một** `List<?>` cho phương thức generic có **một** tham số `List<T>`: khi đó Java chỉ cần capture một kiểu ẩn và dùng nó nhất quán bên trong phương thức.

## 5. Vì sao phép đọc thành Object không chứng minh được quyền ghi?

Mỗi `List<?>` có một kiểu phần tử ẩn. Giá trị từ `get(0)` có thể dùng như `Object`, nhưng Object quá rộng để tự động trở thành kiểu phần tử của danh sách đích:

```java
static void inspect(List<?> left, List<?> right) {
    Object first = left.get(0);
    Object second = right.get(0);
    System.out.println(first + " / " + second);
    // left.add(second); // Không biên dịch: hai capture độc lập.
}
```

Ngay cả `left.add(first)` cũng không tự an toàn theo kiểu tĩnh, vì biến `first` là Object. Ngoại lệ đặc biệt `add(null)` chỉ nói về khả năng gán của null, không bảo đảm danh sách mutable hay chấp nhận null. **Bài toán riêng của hàng này:** cần một mối liên hệ kiểu có thể chứng minh giữa các vị trí wildcard khác nhau. Một generic helper chỉ có thể capture an toàn **một đối số danh sách** và giữ cùng T nội bộ; muốn chuyển phần tử giữa hai danh sách, phải khai báo quan hệ giữa hai kiểu ngay trong API.

## 6. Bắt cùng một kiểu bằng generic helper

Có những phép chỉnh sửa **an toàn** với danh sách chưa biết kiểu, miễn là ta chỉ **di chuyển các phần tử trong chính danh sách đó**, không đưa phần tử của danh sách không liên quan vào.

Ví dụ hoán đổi hai vị trí trong một `List<?>`. Viết trực tiếp rất dễ gặp lỗi capture:

```java
static void swapWrong(List<?> items, int a, int b) {
    // items.set(a, items.get(b)); // LỖI BIÊN DỊCH.
}
```

Giải pháp thông dụng là một phương thức ngoài nhận wildcard và một **generic helper** bên trong đặt tên cho kiểu bị ẩn:

```java
static void swap(List<?> items, int a, int b) {
    swapCaptured(items, a, b);
}

private static <T> void swapCaptured(List<T> items, int a, int b) {
    T oldA = items.get(a);
    items.set(a, items.get(b));
    items.set(b, oldA);
}
```

Cách hoạt động:

1. `swap` nhận `List<?>` nên người gọi có thể truyền `List<String>`, `List<Integer>` hoặc các danh sách kiểu khác.
2. Khi gọi `swapCaptured(items, ...)`, Java capture wildcard và suy luận một `T` phù hợp **cho một đối số `items`**.
3. Trong `swapCaptured`, mỗi lần `get` và `set` cùng làm việc với **một `List<T>`**; lấy `T` từ vị trí này và đặt lại vào vị trí khác là hợp lệ.
4. Phương thức không cần biết `T` chính xác là `String` hay `Integer`, chỉ cần bảo đảm thao tác nội bộ không phá hợp đồng của `T`.

Đây là giải pháp cho **một wildcard của một danh sách**, không biến hai danh sách `List<?>` độc lập thành cùng kiểu. Nó là kỹ thuật *wildcard capture helper* thường dùng khi API cần chấp nhận `List<?>` nhưng một thao tác nội bộ phải giữ liên hệ với đúng kiểu phần tử bị ẩn.

Ngoài kiểm tra generic, vẫn cần bảo đảm chỉ số `a`, `b` hợp lệ và danh sách có thể chỉnh sửa. Nếu không, runtime có thể ném `IndexOutOfBoundsException` hoặc `UnsupportedOperationException`.

## 7. Nếu hai danh sách phải có quan hệ kiểu, hãy biểu diễn bằng `T`

Khi muốn **chuyển phần tử từ danh sách này sang danh sách khác**, cần mô tả chính xác mối quan hệ nguồn–đích.

### 7.1. Yêu cầu cùng đối số kiểu

```java
static <T> void appendFirstSameType(List<T> destination, List<T> source) {
    destination.add(source.get(0));
}
```

`T` ở hai vị trí **là cùng một biến kiểu**. Nếu người gọi có `List<String>` và `List<String>`, lời gọi phù hợp. Nếu người gọi có `List<String>` và `List<Integer>`, Java không thể chọn `T` thỏa cả hai tham số `List<T>` vì generic collections bất biến.

Đối chiếu:

```java
List<String> source = List.of("Java");
List<String> destination = new ArrayList<>();
appendFirstSameType(destination, source); // Hợp lệ.

// List<Integer> integers = new ArrayList<>();
// appendFirstSameType(destination, integers); // LỖI BIÊN DỊCH.
```

Đây là cách thể hiện **yêu cầu cùng kiểu** tại API. Nó khác với hai dấu `?` không ràng buộc.

### 7.2. Nguồn thuộc kiểu con, đích nhận kiểu cha

Đôi khi nguồn là `List<Integer>` và đích là `List<Number>`. Hai loại danh sách **khác nhau**, nhưng vẫn có thể truyền phần tử an toàn vì mỗi `Integer` cũng là một `Number`.

```java
static <T> void appendFirst(
        List<? extends T> source,
        List<? super T> destination) {
    destination.add(source.get(0));
}
```

- `List<? extends T>` cho phép **đọc** phần tử như `T` từ nguồn.
- `List<? super T>` cho phép **ghi** phần tử `T` vào đích.
- **Cùng một `T`** kết nối hai tham số, với wildcard có giới hạn phù hợp.

Đây là ứng dụng của nguyên tắc **PECS**: *Producer Extends, Consumer Super*. Ở đây `source` là nơi cung cấp phần tử; `destination` là nơi nhận phần tử. Trường hợp này không thể diễn tả đầy đủ bằng hai `List<?>` độc lập, vì chúng không cung cấp thông tin về quan hệ kiểu phần tử.

Không nên ép kiểu `(List<Number>)(List<?>) integers` để “chữa” lỗi. Ép kiểu không an toàn không tạo ra quan hệ kiểu thật và có thể làm hỏng hợp đồng của danh sách.

## 8. Ví dụ Java 17+ hoàn chỉnh

Chương trình dưới đây thể hiện đồng thời:

- Hai tham số `List<?>` độc lập có thể nhận hai kiểu danh sách khác nhau.
- Generic helper có thể hoán đổi phần tử **trong cùng danh sách**.
- Generic method có ràng buộc `extends/super` có thể chuyển phần tử từ `List<Integer>` sang `List<Number>`.

Lưu thành **`WildcardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardDemo {
    static void showFirstPair(List<?> left, List<?> right) {
        Object a = left.get(0);
        Object b = right.get(0);
        System.out.println(a + " | " + b);
    }

    static void swap(List<?> items, int a, int b) {
        swapCaptured(items, a, b);
    }

    private static <T> void swapCaptured(List<T> items, int a, int b) {
        T oldA = items.get(a);
        items.set(a, items.get(b));
        items.set(b, oldA);
    }

    static <T> void appendFirst(
            List<? extends T> source,
            List<? super T> destination) {
        destination.add(source.get(0));
    }

    public static void main(String[] args) {
        List<Integer> ints = new ArrayList<>(List.of(10, 20, 30));
        List<String> names = new ArrayList<>(List.of("An", "Binh"));

        List<?> first = ints;
        List<?> second = names;
        showFirstPair(first, second);

        swap(ints, 0, 2);
        swap(names, 0, 1);
        System.out.println(ints);
        System.out.println(names);

        List<Number> numbers = new ArrayList<>();
        appendFirst(ints, numbers);
        System.out.println(numbers);

        showFirstPair(ints, names);
    }
}
```

Biên dịch và chạy:

```bash
javac WildcardDemo.java
java WildcardDemo
```

Stdout:

```text
10 | An
[30, 20, 10]
[Binh, An]
[30]
30 | Binh
```

**Giải thích kết quả:** `first` tham chiếu `List<Integer>` và `second` tham chiếu `List<String>`, nên `showFirstPair` đọc được `10` và `An` như `Object`. `swap` đổi vị trí các phần tử bên trong từng danh sách với đúng kiểu thực của chúng. Sau khi đổi chỗ, số đầu của `ints` là `30`, được thêm hợp lệ vào `numbers` kiểu `List<Number>`. Hai danh sách có kiểu phần tử khác nhau vẫn được xử lý chung khi chỉ cần đọc.

## 9. Không thể “dùng một `T`” để ép hai capture độc lập trở thành cùng kiểu

Có thể bạn sẽ thử giải quyết vấn đề bằng cách đưa cả hai `List<?>` vào một generic helper:

```java
static <T> void copySameType(List<T> to, List<T> from) {
    to.add(from.get(0));
}

static void copyUnknown(List<?> to, List<?> from) {
    copySameType(to, from); // LỖI BIÊN DỊCH.
}
```

`copySameType` tự nó hợp lệ vì yêu cầu hai `List<T>` có **chính xác một `T`**. Nhưng lời gọi `copySameType(to, from)` không thể chứng minh hai capture độc lập của `to` và `from` tương ứng với cùng kiểu. Một helper không thể tự phát minh ra thông tin kiểu mà hai tham số bên ngoài không cung cấp.

Ngay cả trường hợp sau vẫn có thể thất bại:

```java
static void copyUnknown(List<?> items) {
    copySameType(items, items); // LỖI BIÊN DỊCH: hai lần capture độc lập.
}
```

Khác biệt quan trọng:

- `swapCaptured(items)` chỉ nhận **một `List<T>`**; sau khi capture, mọi phép đọc/ghi trong helper đều dùng cùng `T`.
- `copySameType(items, items)` có **hai vị trí đối số** cùng phải phù hợp với một `T`; từ biểu thức `List<?>`, capture của từng vị trí không mặc nhiên là cùng kiểu.
- `copySameType(typed, typed)` với `typed` khai báo là `List<Integer>` thì hợp lệ vì loại `Integer` đã được thể hiện trong hệ kiểu.

Khi tác vụ thực sự đòi hỏi quan hệ giữa hai tham số, nên đặt quan hệ ấy ở **chữ ký API đầu vào**, bằng `<T>` và các giới hạn cần thiết. Nếu chỉ xử lý nội bộ một danh sách chưa biết kiểu, hãy dùng capture helper với **một danh sách**.

## 10. `Map<?, ?>`: hai wildcard trong cùng một kiểu generic

Tình huống tương tự xuất hiện khi một kiểu generic có **nhiều đối số kiểu**:

```java
Map<?, ?> data = Map.of("language", 17);
Object key = data.keySet().iterator().next();
Object value = data.values().iterator().next();
```

Dấu `?` thứ nhất mô tả kiểu khóa chưa biết; dấu `?` thứ hai mô tả kiểu giá trị chưa biết. Không có điều kiện mặc định rằng **kiểu khóa phải bằng kiểu giá trị**. Ví dụ `Map<String, Integer>` và `Map<Long, Long>` đều có thể được tham chiếu bằng `Map<?, ?>`.

Trong phần lớn thao tác ghi, ta không thể đưa một khóa hoặc giá trị không-null bất kỳ vào `Map<?, ?>`, vì kiểu ẩn của chúng chưa được biết. Tư duy này cũng áp dụng cho `BiFunction<?, ?, ?>` và các generic type có nhiều dấu `?`: **mỗi vị trí wildcard cần được xét theo ràng buộc riêng**.

## 11. Những nhầm lẫn dễ gặp

### “Dùng cùng ký hiệu `?` nghĩa là cùng kiểu”

**Sai.** `?` không phải biến có tên dùng lại như `T`. Hai wildcard khác nhau không tự sinh ra ràng buộc bằng nhau. Có thể ở runtime chúng liên quan đến cùng một loại phần tử, nhưng trình biên dịch cần chứng cứ tĩnh được biểu diễn qua kiểu.

### “Hai danh sách đều `List<?>` nên thêm từ bên này sang bên kia được”

**Sai.** Cả hai cùng tương thích với kiểu giao diện `List<?>` để **đọc**, không có nghĩa kiểu phần tử của chúng tương thích để **ghi**. Ví dụ `List<Integer>` và `List<String>` đều gán được cho `List<?>` nhưng không thể chuyển phần tử tùy ý giữa chúng.

### “Một danh sách khai báo `List<?>` có thể chứa đủ mọi loại đối tượng”

**Sai theo cách hiểu về khả năng ghi.** `List<?>` tham chiếu một danh sách có kiểu phần tử cụ thể chưa biết; điều đó không cấp quyền thêm mọi loại đối tượng. Nếu muốn một danh sách có phần tử mang nhiều kiểu khác nhau và cần thêm đối tượng bất kỳ, có thể dùng `List<Object>` khi thiết kế bài toán thật sự đòi hỏi như vậy.

### “Một helper generic sẽ làm hai kiểu ẩn tự động thống nhất”

**Sai.** Helper chỉ giúp Java **đặt tên một capture** và áp dụng nó nhất quán trong thân phương thức. Nếu nhận hai danh sách chưa có quan hệ kiểu, không thể khẳng định một `T` chung bằng cách gọi helper một cách mù quáng.

### “`List<?>` là immutable”

**Sai.** Kiểu wildcard và tính có thể chỉnh sửa của collection là hai vấn đề độc lập. Một `ArrayList<String>` thông qua `List<?>` có thể `clear()`, còn `List.of(1, 2)` có thể từ chối chỉnh sửa dù tham chiếu được khai báo với `List<Integer>` cụ thể.

### “Type erasure khiến các wildcard không khác nhau”

**Sai.** Type erasure ảnh hưởng đến cách biểu diễn generic ở runtime; các phép gán, capture và ràng buộc kiểu vẫn được **trình biên dịch Java** áp dụng trước khi chạy. Không thể lấy việc nhiều `List<T>` cùng bị xóa đối số generic để suy ra có thể trao đổi phần tử giữa hai `List<?>`.

## 12. Tự kiểm tra

Với các khai báo sau, hãy xét **khả năng biên dịch**, giả sử phương thức được gọi trên danh sách không rỗng khi đọc:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<String> texts = new ArrayList<>(List.of("A", "B"));
List<?> a = ints;
List<?> b = texts;
```

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `Object x = a.get(0);` | Hợp lệ | Đọc `List<?>` ra `Object` |
| `String s = b.get(0);` | Lỗi biên dịch | `b.get(0)` chỉ bảo đảm một kiểu chưa biết, dùng an toàn như `Object` |
| `a.add(b.get(0));` | Lỗi biên dịch | Không chứng minh được hai wildcard có kiểu tương thích |
| `a.set(0, a.get(0));` | Lỗi biên dịch | Hai lần capture có thể độc lập; cần generic helper |
| `a.add(null);` | Hợp lệ về kiểu | `null` được chấp nhận về kiểu; runtime tùy collection |
| `showFirstPair(a, b);` | Hợp lệ | Phương thức chỉ đọc hai danh sách dưới dạng `Object` |
| `swap(ints, 0, 1);` | Hợp lệ | Generic helper xử lý một danh sách kiểu `Integer` |
| `appendFirst(ints, new ArrayList<Number>());` | Hợp lệ | `Integer` có thể được thêm vào đích nhận `Number` |

Chú ý: “hợp lệ về kiểu” không bảo đảm chạy luôn thành công; ví dụ `get(0)` trên danh sách rỗng vẫn ném `IndexOutOfBoundsException`, hoặc `add(null)` trên collection không hỗ trợ chỉnh sửa vẫn có thể ném ngoại lệ.

## Ghi nhớ

1. `?` là **một kiểu tham số chưa biết**, không phải một biến chung mang tên `?`.
2. **Mỗi wildcard/capture có thể tương ứng với một kiểu khác nhau**; chúng cũng có thể trùng nhau, nhưng trình biên dịch không tự giả định quan hệ bằng nhau.
3. `List<?>` cho phép **đọc ra `Object`**; nó không bảo đảm có thể ghi phần tử không-null thuộc một kiểu cụ thể.
4. Khi cần thao tác bên trong **một danh sách** mà phải giữ nguyên kiểu phần tử, dùng generic helper để capture thành `List<T>`.
5. Khi cần thao tác giữa **hai danh sách có quan hệ kiểu**, hãy mô tả quan hệ bằng `<T>`, `? extends T` và `? super T`, thay vì chỉ đưa cả hai về `List<?>`.

Hiểu tính độc lập của mỗi dấu `?` giúp giải thích các lỗi `capture of ?` trong Java và lựa chọn chữ ký generic chính xác cho API, vừa linh hoạt khi đọc dữ liệu vừa bảo vệ an toàn kiểu lúc ghi.
