# Đặt tên kiểu chưa biết bằng phương thức hỗ trợ generic (wildcard capture)

## 1. Wildcard capture giải quyết vấn đề gì?

Trong Java Generics, ký hiệu `?` cho biết một đối số kiểu **cụ thể nhưng chưa biết** tại nơi sử dụng, chẳng hạn `List<?>`, `List<? extends Number>` hoặc `List<? super Integer>`. Ta vẫn có thể đọc dữ liệu theo những bảo đảm của giới hạn kiểu, nhưng nhiều thao tác ghi bị từ chối vì trình biên dịch không thể chứng minh giá trị được ghi đúng kiểu phần tử ẩn.

Ví dụ:

```java
import java.util.List;

static void replaceWithSameValue(List<?> values) {
    values.set(0, values.get(0)); // LỖI BIÊN DỊCH
}
```

Người lập trình thấy cùng một danh sách được đọc và ghi, nhưng ở cấp độ kiểm tra kiểu, biểu thức `get(0)` không được bảo đảm có đúng một kiểu mà lời gọi `set(0, ...)` yêu cầu khi wildcard được capture qua các ngữ cảnh sử dụng khác nhau. Vì thế Java không chấp nhận mã này.

Để diễn đạt mối quan hệ “giá trị lấy ra và vị trí ghi vào thuộc **cùng kiểu phần tử**”, ta sử dụng **phương thức hỗ trợ generic** (*generic helper method*) có tham số kiểu đặt tên:

```java
static <E> void replaceHelper(List<E> values) {
    if (!values.isEmpty()) {
        E current = values.get(0);
        values.set(0, current); // Hợp lệ: get và set dùng cùng E
    }
}

static void replace(List<?> values) {
    replaceHelper(values); // Trình biên dịch bắt giữ wildcard thành E
}
```

Trong lời gọi `replaceHelper(values)`, Java thực hiện **capture conversion** để coi đối số wildcard chưa biết là một tham số kiểu tạm thích hợp khi suy luận kiểu `E`. Bên trong helper, cùng tên `E` được sử dụng nhất quán ở `List<E>`, `get` và `set`.

Đây là kỹ thuật **đặt tên cho kiểu chưa biết bằng phương thức hỗ trợ generic**. Tên `E` chỉ tồn tại trong phạm vi helper; không có chuyện wildcard bị thay đổi vĩnh viễn thành `Object` hay thành một kiểu được người lập trình đoán trước.

## 2. Wildcard `?` và tham số kiểu `<E>` khác nhau thế nào?

Xét hai chữ ký:

```java
static void inspect(List<?> list) { /* ... */ }

static <E> void transform(List<E> list) { /* ... */ }
```

Cả hai có thể nhận `List<String>`, `List<Integer>` và nhiều kiểu danh sách khác. Khác biệt nằm ở thông tin kiểu có thể sử dụng **trong thân phương thức**.

| Đặc điểm | `List<?>` | `<E> ... (List<E>)` |
| --- | --- | --- |
| Kiểu phần tử | Một kiểu chưa biết | Một kiểu được đặt tên `E` |
| Đọc bằng `get` | Có thể nhận an toàn như `Object` | Nhận an toàn dưới `E` |
| Thêm giá trị cụ thể từ ngoài | Không được phép tùy ý | Chỉ được nếu giá trị đã được chứng minh là `E` |
| Đọc rồi ghi lại cùng giá trị | Biểu thức trực tiếp với wildcard có thể lỗi capture | Có thể giữ giá trị trong biến `E` và ghi lại |
| Liên hệ các vị trí kiểu | Không đặt tên trực tiếp cho `?` | Một `E` có thể dùng tại nhiều vị trí |
| Bảo đảm sửa đổi runtime | Không | Không; phụ thuộc triển khai danh sách |

`<E>` là **khai báo một tham số kiểu mới** cho phương thức. Nó không đòi caller phải viết rõ kiểu `E`: trình biên dịch thường tự suy luận qua đối số và áp dụng capture conversion.

Ví dụ, `List<?> unknown = new ArrayList<String>();` có thể gọi `transform(unknown)` nếu thân `transform` chỉ thực hiện các thao tác an toàn trên cùng một `E`. Trình biên dịch **không kết luận `E = String` dựa vào đối tượng runtime**; nó coi `E` là kiểu ẩn phù hợp của lời gọi.

## 3. Mô hình capture conversion: kiểu chưa biết có danh tính trong một phạm vi

Trình biên dịch thường mô tả wildcard qua ký hiệu kiểu nội bộ như `CAP#1`. Với:

```java
List<?> items = new ArrayList<String>();
```

ta có thể hình dung `items` là danh sách chứa một kiểu `CAP#1` chưa biết, có giới hạn trên `Object`. Đây là ký hiệu diễn giải, **không phải** cú pháp Java có thể viết trực tiếp trong mã nguồn.

```text
Kiểu khai báo tại caller:
    List<?>

Capture conversion tại một lời gọi thích hợp:
    ?  -> CAP#1 (kiểu chưa biết, có danh tính nội bộ)

Suy luận tham số kiểu của helper:
    E  = CAP#1

Trong helper:
    E value = list.get(0)
    list.set(0, value)
    // Cả nơi đọc và nơi ghi đều dùng E.
```

Không nên hiểu dấu `?` là “`Object`” hoặc là “mỗi phần tử có thể mang một kiểu tùy ý”. Đối tượng thật vẫn giữ hợp đồng `List<String>`, `List<Integer>` hoặc kiểu tương ứng. `Object` chỉ là kiểu chung an toàn khi ta đọc từ `List<?>` mà chưa biết thêm điều gì về phần tử.

Thông điệp của lỗi biên dịch có thể nhắc tới `capture of ?` hoặc `CAP#1`, `CAP#2`. Các số đánh dấu này chỉ là tên nội bộ để trình bày sự không thống nhất kiểu ở nơi compiler phát hiện lỗi; không dùng chúng để khai báo biến Java.

### Vì sao cần một helper?

Một helper là nơi lập trình viên **khai báo cùng một `E` xuất hiện ở cả hai vị trí liên quan**. Trình biên dịch có thể chứng minh mọi thao tác trong helper không đưa phần tử sai kiểu vào danh sách. Khi caller có `List<?>`, suy luận kiểu của lời gọi sẽ capture wildcard một cách an toàn.

Helper không làm các phép ép kiểu không an toàn trở nên hợp lệ; nó chỉ biểu đạt đúng mối quan hệ đã tồn tại giữa những phần tử của một đối tượng generic.

## 4. Thiết kế ranh giới API ngoài và generic helper bên trong

Một helper không chỉ dùng cho thao tác hoán đổi. Ví dụ **sao chép phần tử đầu vào vị trí cuối trong cùng list**:

```java
static void copyFirstToLast(List<?> values) {
    copyCaptured(values);
}

private static <E> void copyCaptured(List<E> values) {
    if (values.size() >= 2) {
        E first = values.get(0);
        values.set(values.size() - 1, first);
    }
}
```

Đây là các method minh họa đặt trong class có import `java.util.List`. Nếu dữ liệu ban đầu là `[A, B, C]` trong `ArrayList<String>`, kết quả là `[A, B, A]`. Nếu là `[1, 2, 3]` trong `ArrayList<Integer>`, kết quả là `[1, 2, 1]`.

**Tại biên API**, `List<?>` cho phép caller truyền danh sách của bất kỳ element type. **Trong helper**, `List<E>` kết nối `get` và `set` bằng cùng một `E`; compiler không cần biết `E` là String hay Integer. Không thể thay `first` bằng một `Object` lấy tùy ý từ ngoài list.

Một ví dụ khác của kỹ thuật này là swap hai vị trí; Java đã có `Collections.swap(List<?>,i,j)`. Khi chỉ cần swap, hãy ưu tiên API chuẩn; khi cần một thuật toán riêng như trên, generic helper giúp trình bày bất biến kiểu rõ hơn. Nếu list không hỗ trợ `set`, runtime vẫn có thể ném `UnsupportedOperationException`.

## 5. Thêm lại phần tử đang có: một thao tác có thể hợp lệ trong helper

Mã trực tiếp sau có lỗi kiểu:

```java
static void duplicateWrong(List<?> values) {
    values.add(values.get(0)); // LỖI BIÊN DỊCH
}
```

Có thể giữ kiểu phần tử cùng một `E` bằng helper:

```java
static <E> void duplicateCaptured(List<E> values) {
    if (!values.isEmpty()) {
        E first = values.get(0);
        values.add(first); // Đúng ở cấp độ generic
    }
}

static void duplicateFirst(List<?> values) {
    duplicateCaptured(values);
}
```

Ở đây `first` **được lấy từ chính danh sách**, không phải một `Object` hay `String` bất kỳ đến từ bên ngoài. Nếu `values` thực chất là `List<Integer>`, helper chỉ nhân bản phần tử `Integer` có sẵn. Nếu là `List<String>`, helper nhân bản `String`.

Cần phân biệt rõ hai điều:

- Helper hợp lệ về **kiểu** vì sử dụng cùng một `E`.
- `add` vẫn có thể thất bại ở **runtime** nếu danh sách cố định kích thước hoặc không cho sửa đổi (`Arrays.asList`, `List.of`).

Còn nếu danh sách rỗng, mã trên chủ động không làm gì để tránh `IndexOutOfBoundsException`.

### Capture không cấp quyền thêm một giá trị bên ngoài tùy ý

Không thể viết:

```java
static void addString(List<?> unknown) {
    addCaptured(unknown, "Java"); // Không đảm bảo biên dịch
}

static <E> void addCaptured(List<E> list, E value) {
    list.add(value);
}
```

Vì không thể chứng minh `unknown` là `List<String>`. Tại lời gọi `addCaptured(unknown, "Java")`, các ràng buộc kiểu của `List<E>` và `E value` không có một cách gán hợp lệ chỉ dựa trên `List<?>`; `E` bị giới hạn bởi kiểu phần tử ẩn, không thể tùy tiện coi là `String`.

Để thực sự thêm `String` vào một đích có thể nhận nó, hãy thay hợp đồng API:

```java
static void addText(List<? super String> destination, String text) {
    destination.add(text);
}
```

Đích có thể là `List<String>`, `List<CharSequence>` hoặc `List<Object>`, và mọi kiểu đó đều tiếp nhận `String`. Không cần wildcard capture helper khi quan hệ giữa giá trị ghi và đích đã được nêu đầy đủ bằng giới hạn dưới.

## 6. Helper với wildcard có giới hạn trên `? extends T`

Cơ chế tương tự khi đối số không phải `?` trần mà là wildcard có bound:

```java
static void repeatLastNumber(List<? extends Number> values) {
    repeatNumberCaptured(values);
}

private static <E extends Number> void repeatNumberCaptured(List<E> values) {
    if (!values.isEmpty()) {
        E last = values.get(values.size() - 1);
        values.add(last);
    }
}
```

Lời gọi `repeatNumberCaptured(values)` cho phép trình biên dịch capture kiểu phần tử ẩn dưới giới hạn `Number`; `E` đồng thời bị giới hạn trên bởi `Number`.

Trong helper, có thể dùng:

```java
E number = values.get(0);
double d = number.doubleValue(); // Đúng: E extends Number
```

Nhưng không thể thêm một `Integer` tùy ý:

```java
static <E extends Number> void invalid(List<E> values) {
    values.add(Integer.valueOf(10)); // LỖI BIÊN DỊCH
}
```

Vì `E` có thể là `Double`, `BigDecimal` hoặc một kiểu con khác của `Number`. Capture giải quyết danh tính của một kiểu ẩn **đã có**, không cho phép giả định kiểu ấy là một subtype cụ thể nào đó.

Nếu chỉ cần thao tác với phần tử như `Number`, việc dùng `<E extends Number>` trong helper là phù hợp. Nếu chỉ cần chuyển phần tử giữa các vị trí của cùng danh sách, một helper `<E>` không bound cũng đủ; đừng thêm bound khi không có lý do.

## 7. Trường hợp giới hạn dưới `? super T`: capture không làm phần tử đọc ra thành T

Với:

```java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(7); // Có thể thêm Integer
Object result = sink.get(0); // Chỉ được bảo đảm là Object
```

Wildcard của `sink` có giới hạn dưới `Integer`. Kiểu phần tử thực tế có thể là `Integer`, `Number`, `Object` hoặc supertype phù hợp khác. Do đó không thể đọc trực tiếp `Integer` từ `sink`.

Một helper generic nhận `List<E>` cũng không được phép giả định `E` chính xác là `Integer`:

```java
static <E> void inspectCaptured(List<E> list) {
    E element = list.get(0); // Hợp lệ
    // Integer n = element; // LỖI: E không biết có phải Integer hay không
}
```

Việc có thể chuyển `List<? super Integer>` vào helper và giữ kiểu `E` không làm giới hạn dưới chuyển thành giới hạn trên `Integer`. **Kiểu đầu ra bảo đảm** qua wildcard dưới vẫn là `Object`, trừ khi API cung cấp thêm chứng cứ kiểu độc lập.

Mặt khác, nếu helper chỉ muốn đưa **phần tử đã có** trở lại đúng danh sách, nó vẫn có thể sử dụng một `E` nhất quán; đó là tính an toàn của thao tác nội bộ, không phải khả năng đọc một `Integer` bên ngoài helper.

## 8. Capture trong phương thức generic và suy luận kiểu

Ví dụ:

```java
static <E> E first(List<E> list) {
    return list.get(0);
}

static Object readUnknown(List<?> values) {
    return first(values);
}
```

Trình biên dịch có thể capture wildcard trong `values` thành một kiểu chưa biết để suy luận `E` tại lời gọi `first(values)`. Giá trị trả về là chính kiểu đã capture, nhưng nơi gọi chỉ biết gán an toàn thành `Object` khi xuất phát từ `List<?>`.

Trường hợp có giới hạn trên:

```java
static Number readNumber(List<? extends Number> values) {
    return first(values);
}
```

Đây là phép trả về hợp lệ vì kiểu đã capture có giới hạn trên `Number`.

Đáng chú ý: generic helper **không bắt người gọi biết tên kiểu thực tế**. Trong thực tế các phương thức generic của Java dùng type inference và capture conversion rất nhiều, kể cả khi không thấy compiler thông báo `CAP#1`.

### Mỗi tham số wildcard độc lập không tự thành cùng một E

Xét:

```java
static void moveBad(List<?> source, List<?> destination) {
    destination.add(source.get(0)); // LỖI BIÊN DỊCH
}
```

Hai wildcard ở `source` và `destination` có thể biểu diễn **hai kiểu phần tử khác nhau**. Chúng không mặc nhiên được capture thành **cùng một `E`**.

Ngay cả khi cả hai biến tình cờ cùng trỏ tới một `List<String>` ở runtime, chữ ký `List<?>, List<?>` không diễn đạt quan hệ ấy. Helper `<E>` không thể “ép buộc” hai capture độc lập phải cùng kiểu nếu caller chưa cung cấp quan hệ kiểu an toàn.

Nếu nhu cầu là chuyển phần tử từ nguồn sang đích rộng hơn, hãy **diễn đạt đúng quan hệ** bằng PECS:

```java
static <E> void copyTo(
        List<? extends E> source,
        List<? super E> destination) {
    for (E value : source) {
        destination.add(value);
    }
}
```

Khi đó `List<Integer>` có thể được đọc và chuyển vào `List<Number>` hoặc `List<Object>`; nhưng hai danh sách `List<?>` độc lập không đủ chứng minh quan hệ cần thiết.

Không nên dùng raw type, ép kiểu unchecked hoặc `@SuppressWarnings("unchecked")` để giả vờ hai danh sách có cùng kiểu. Các cách đó có thể làm sai hợp đồng phần tử và gây lỗi ép kiểu muộn.

## 9. Khi nào nên dùng helper và khi nào không?

Dùng helper generic khi:

1. API bên ngoài nhận một `List<?>` hoặc `List<? extends T>` đủ linh hoạt.
2. Một nhóm thao tác **cần giữ cùng kiểu phần tử ẩn** qua nhiều vị trí trong thân hàm.
3. Giá trị ghi lại được lấy từ chính danh sách hoặc qua phép biến đổi đã được ràng buộc `E -> E`.
4. Có thể thực hiện thao tác mà không đoán kiểu cụ thể, không dùng cast unchecked.

Không cần helper nếu:

- API chỉ đọc phần tử qua `List<? extends T>`, không ghi trở lại.
- API chỉ ghi giá trị `T` vào `List<? super T>`.
- API đã dùng `<T> void process(List<T> list, ...)` và các vị trí đã liên hệ cùng một `T`.
- Có sẵn một API chuẩn thể hiện chính xác thao tác, chẳng hạn `Collections.swap` hoặc `Collections.reverse`.

Bảng chọn nhanh:

| Nhu cầu | Chữ ký gợi ý |
| --- | --- |
| Chỉ quan sát một danh sách chưa biết kiểu | `void inspect(List<?> list)` |
| Hoán đổi các phần tử của một danh sách kiểu chưa biết | `void swap(List<?> list)` gọi helper `<E>`, hoặc `Collections.swap` |
| Đọc rồi ghi lại đúng kiểu phần tử ẩn | `void update(List<?> list)` gọi helper `<E>` |
| Đọc và xử lý như `Number` | `void inspect(List<? extends Number> list)` |
| Biến đổi phần tử cùng kiểu `E` | `<E> void update(List<E> list, UnaryOperator<E> f)` |
| Thêm `String` vào danh sách có thể chứa `String` | `void write(List<? super String> sink)` |
| Sao chép nguồn sang đích tương thích | `<E> void copy(List<? extends E> src, List<? super E> dst)` |

Nếu triển khai helper gọi `add` hoặc `set`, danh sách phải hỗ trợ phép thay đổi đó ở runtime. `List.of` thường không cho sửa; `Arrays.asList` cho `set` nhưng không cho `add` thay đổi kích thước. Giới hạn kiểu là câu chuyện **biên dịch**, còn khả năng thay đổi cấu trúc và nội dung thuộc **hợp đồng đối tượng**.

## 10. Chương trình Java 17+ đầy đủ

Tạo tệp **`CaptureExample.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureExample {
    // API bên ngoài nhận danh sách chưa biết kiểu.
    static void reorder(List<?> items) {
        if (items.size() > 1) {
            swap(items, 0, 1);
        }
    }

    // Helper đặt tên E cho kiểu đã được capture.
    private static <E> void swap(
            List<E> items, int left, int right) {
        E old = items.get(left);
        items.set(left, items.get(right));
        items.set(right, old);
    }

    static void duplicateUnknown(List<?> items) {
        duplicate(items);
    }

    private static <E> void duplicate(List<E> items) {
        if (!items.isEmpty()) {
            E first = items.get(0);
            items.add(first);
        }
    }

    // Wildcard có giới hạn trên được capture trong helper.
    static void repeatNumber(List<? extends Number> items) {
        repeatLast(items);
    }

    private static <E extends Number> void repeatLast(List<E> items) {
        if (!items.isEmpty()) {
            E last = items.get(items.size() - 1);
            items.add(last);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("red", "green", "blue"));
        List<?> unknown = words;

        reorder(unknown);
        System.out.println("Swapped: " + words);

        duplicateUnknown(unknown);
        System.out.println("Duplicated: " + words);

        List<Integer> integers = new ArrayList<>(List.of(2, 4));
        List<? extends Number> numbers = integers;

        repeatNumber(numbers);
        System.out.println("Numbers: " + integers);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 CaptureExample.java
java CaptureExample
```

Đầu ra:

```text
Swapped: [green, red, blue]
Duplicated: [green, red, blue, green]
Numbers: [2, 4, 4]
```

Giải thích:

- `unknown` có kiểu `List<?>`, nên phía ngoài không biết phần tử là `String`. Lời gọi `reorder(unknown)` vẫn đúng: `swap` giữ cùng `E` khi đọc và ghi qua `set`.
- `duplicateUnknown` capture kiểu ẩn một lần trong lời gọi `duplicate(items)`; phần tử mới là phần tử có sẵn, đã đúng `E`.
- `repeatNumber` nhận `List<? extends Number>` và dùng helper `<E extends Number>` để nhân bản phần tử cuối. Kiểu phần tử thực tế vẫn là `Integer`, nên `[2, 4]` thành `[2, 4, 4]`.
- Tất cả danh sách được thay đổi ở ví dụ đều là `ArrayList`, có hỗ trợ `set` và `add`. Biến wildcard chỉ là góc nhìn có kiểu tĩnh rộng hơn lên cùng đối tượng.

Các phương thức helper trên an toàn mà **không cần raw type, unchecked cast hoặc suppress warning**.

## 11. Lỗi phổ biến và cách sửa

| Lỗi hoặc suy luận sai | Giải thích | Cách sửa |
| --- | --- | --- |
| `list.set(0, list.get(0))` trên `List<?>` được cho là luôn biên dịch | Những vị trí wildcard trong biểu thức không được ràng buộc theo cùng `E` | Đưa cả `get` và `set` vào `<E> helper(List<E>)` |
| Thấy `List<?>` là coi kiểu phần tử bằng `Object` | Kiểu thật có thể là `String`, `Integer`, v.v. | Hiểu `?` là kiểu chưa biết; chỉ **đọc** an toàn dưới `Object` |
| Dùng helper `<E>` để thêm một `String` bất kỳ vào `List<?>` | Không có chứng cứ kiểu `E` nhận `String` | Dùng `List<? super String>` khi cần ghi `String` |
| Coi hai `List<?>` khác nhau có cùng capture | Hai wildcard độc lập không nhất thiết cùng kiểu | Khai báo quan hệ bằng `List<E>` hoặc cặp PECS `? extends E` / `? super E` |
| Nghĩ helper cho phép mọi thao tác sửa đổi | Compiler chỉ kiểm tra kiểu, danh sách runtime có thể không hỗ trợ `add/set` | Xem hợp đồng implementation và trường hợp ngoại lệ |
| Dùng cast unchecked thay helper | Cast không chứng minh kiểu phần tử thật, có nguy cơ heap pollution | Dùng phương thức generic giữ đúng cùng `E` |
| Tạo helper chỉ để gọi `get` rồi trả `Object` | Không có nhu cầu giữ liên hệ giữa nhiều vị trí `E` | Dùng trực tiếp `List<?>` và `Object` |
| Tưởng `<E extends Number>` cho phép thêm mọi `Number` | `E` vẫn có thể là `Integer` hoặc `Double` | Chỉ ghi giá trị được chứng minh đúng `E` |

## 12. Bài tập tự kiểm tra

Các đoạn sau xét **riêng lẻ**. Giả sử đã import `java.util.*`. Nếu có khai báo `static`, hãy đặt phương thức vào thân một lớp Java; các đoạn này không phải tệp Java độc lập.

**A — Gán lại giá trị lấy từ wildcard**

```java
static void a(List<?> list) {
    list.set(0, list.get(0));
}
```

**B — Đưa thao tác vào helper**

```java
static <E> void bHelper(List<E> list) {
    if (!list.isEmpty()) {
        list.set(0, list.get(0));
    }
}
static void b(List<?> list) {
    bHelper(list);
}
```

**C — Helper thêm giá trị cụ thể vào wildcard**

```java
static <E> void addHelper(List<E> list, E x) {
    list.add(x);
}
static void c(List<?> list) {
    addHelper(list, "hello");
}
```

**D — Capture danh sách số có giới hạn trên**

```java
static <E extends Number> void doubleLast(List<E> list) {
    if (!list.isEmpty()) {
        list.add(list.get(list.size() - 1));
    }
}
static void d(List<? extends Number> list) {
    doubleLast(list);
}
```

**E — Hai wildcard độc lập**

```java
static void e(List<?> left, List<?> right) {
    right.add(left.get(0));
}
```

**F — Dùng PECS với hai vai trò riêng biệt**

```java
static <E> void f(
        List<? extends E> source,
        List<? super E> destination) {
    for (E value : source) {
        destination.add(value);
    }
}
```

**G — Có helper nhưng danh sách không sửa được**

```java
static <E> void gHelper(List<E> list) {
    if (!list.isEmpty()) {
        list.add(list.get(0));
    }
}
static void g() {
    gHelper(List.of(1, 2));
}
```

**Đáp án:**

- **A:** Không biên dịch; kiểu trả về của `get` không được chấp nhận ở vị trí `set` vì không giữ được quan hệ capture cần thiết.
- **B:** Biên dịch. `bHelper` dùng cùng `E` cho cả thao tác đọc và ghi; nếu danh sách không hỗ trợ `set`, runtime vẫn có thể từ chối.
- **C:** Không biên dịch tại lời gọi `addHelper(list, "hello")`; không thể chứng minh kiểu phần tử ẩn là `String`.
- **D:** Biên dịch. `E` capture kiểu phần tử số chưa biết và giữ đúng kiểu khi nhân bản phần tử cuối; runtime cần hỗ trợ `add`.
- **E:** Không biên dịch; kiểu phần tử của `left` không có quan hệ được chứng minh với kiểu phần tử của `right`.
- **F:** Biên dịch; nguồn cung cấp `E`, đích chấp nhận `E`. Khi gọi, compiler vẫn kiểm tra cặp đối số có quan hệ kiểu phù hợp.
- **G:** Biên dịch nhưng `List.of` không hỗ trợ thêm phần tử; lúc chạy ném `UnsupportedOperationException`.

## 13. Ghi nhớ

**Wildcard capture** là cơ chế trình biên dịch dùng để biểu diễn một kiểu wildcard chưa biết thành một kiểu tạm có danh tính và giới hạn phù hợp. **Generic helper `<E>`** cho phép mã nguồn đặt tên kiểu đó và gắn các vị trí `get`, `set`, `add` vào cùng một tham số kiểu.

Mẫu thường dùng:

```java
static void publicOperation(List<?> values) {
    helper(values);
}

private static <E> void helper(List<E> values) {
    // Đọc và ghi các giá trị đã được chứng minh có cùng kiểu E.
}
```

Kỹ thuật này không biến `List<?>` thành `List<Object>`, không cho chèn một giá trị bất kỳ từ bên ngoài và không chứng minh hai wildcard độc lập có cùng kiểu. Nó bảo toàn an toàn kiểu khi thuật toán cần **đọc rồi ghi lại phần tử có cùng kiểu thực tế**. Khi thiết kế API nguồn/đích riêng biệt, hãy diễn đạt quan hệ bằng `? extends E` và `? super E`; khi chỉ cần thao tác chuẩn, ưu tiên dùng API thư viện đã có.
