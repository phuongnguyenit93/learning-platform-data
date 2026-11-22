# Phép chuyển đổi bắt giữ (capture conversion) giải quyết vấn đề gì trong Java Generics?

**Capture conversion** là cơ chế của trình biên dịch Java giúp xử lý một kiểu generic có **wildcard** (`?`, `? extends T`, `? super T`) như một **kiểu chưa biết nhưng xác định trong một ngữ cảnh kiểm tra kiểu**. Trình biên dịch tạm đặt một tên kiểu nội bộ cho dấu `?`, thường hiển thị trong thông báo lỗi dưới dạng `capture#1 of ?` hoặc `CAP#1`. Nhờ vậy, phương thức generic có thể duy trì mối liên hệ giữa **phần tử lấy ra** và **phần tử đưa trở lại chính collection ấy**, dù mã gọi không biết đối số kiểu thực sự.

Vấn đề capture conversion giải quyết không phải “biến `List<?>` thành `List<Object>`”. Nó giải quyết việc **giữ một kiểu ẩn nhất quán trong một lần xử lý**, cho phép các thao tác thật sự an toàn với một collection có kiểu phần tử chưa biết.

Một ví dụ cốt lõi:

```java
static void swap(List<?> items, int i, int j) {
    swapCaptured(items, i, j);
}

private static <T> void swapCaptured(List<T> items, int i, int j) {
    T saved = items.get(i);
    items.set(i, items.get(j));
    items.set(j, saved);
}
```

`swap` nhận được `List<String>`, `List<Integer>`, `List<Number>` và nhiều kiểu danh sách khác. `swapCaptured` sử dụng **một biến kiểu `T` cho toàn bộ thao tác trong một danh sách**, nên đọc rồi ghi lại một phần tử đúng loại mà không cần ép kiểu không an toàn.

## 1. Bài toán: Java biết “có một kiểu” nhưng chưa biết tên kiểu đó

Ví dụ:

```java
List<Integer> integers = new ArrayList<>(List.of(10, 20));
List<?> unknown = integers;
```

Ở runtime, danh sách chứa các đối tượng `Integer`. Tuy nhiên, theo kiểu khai báo `List<?>` của `unknown`, trình biên dịch chỉ biết đối số kiểu là **một kiểu tham chiếu chưa xác định**.

Các thao tác đọc đơn giản vẫn an toàn:

```java
Object element = unknown.get(0);  // Hợp lệ.
int length = unknown.size();      // Hợp lệ.
```

Ngược lại, hai thao tác này bị từ chối:

```java
// unknown.add(10);            // LỖI BIÊN DỊCH.
// unknown.set(0, unknown.get(0)); // LỖI BIÊN DỊCH.
```

Lệnh `add(10)` không an toàn nói chung, vì `unknown` có thể trỏ tới `List<String>`. Nhưng `set(0, unknown.get(0))` lại có vẻ hợp lý: lấy phần tử ở chính danh sách đó rồi đặt nó trở lại cùng vị trí, không thể đưa một kiểu khác vào.

**Vấn đề nằm ở thông tin kiểu mà biểu thức cung cấp cho trình biên dịch.** Qua `List<?>`, kết quả `get(0)` có kiểu phần tử ẩn; trong kiểm tra lời gọi `set`, Java không tự đồng nhất kiểu capture ở hai lần xuất hiện wildcard thành một kiểu được đặt tên và sử dụng ổn định. Vì thế, biểu thức `unknown.set(0, unknown.get(0))` không biên dịch, dù ý tưởng thao tác là an toàn khi hai lần truy cập thật sự thuộc cùng một danh sách.

Cần một cách **đặt tên cho kiểu phần tử chưa biết**, để chứng minh giá trị đọc ra có thể ghi trở lại đúng nơi đã tạo ra nó. Capture conversion kết hợp generic helper làm được điều này.

## 2. Capture conversion là gì?

Xét kiểu:

```java
List<?> values;
```

Theo cách hình dung đơn giản, khi Java cần kiểm tra một biểu thức kiểu `List<?>`, nó có thể mở wildcard thành một **biến kiểu mới do trình biên dịch sinh ra**:

```text
List<?>            --capture conversion-->  List<CAP#1>

CAP#1 là một kiểu chưa biết, có giới hạn trên là Object.
```

Tên `CAP#1` chỉ để minh họa; người lập trình không khai báo hay tham chiếu trực tiếp được `CAP#1` trong mã nguồn. Thông báo lỗi của các phiên bản `javac` có thể gọi nó là `capture#1 of ?` hoặc dùng số khác.

Điều quan trọng không nằm ở giá trị tên này, mà ở quan hệ kiểu:

- Một phần tử được lấy ra từ `List<CAP#1>` có kiểu `CAP#1`.
- Một phương thức nhận `List<CAP#1>` có thể sử dụng `CAP#1` như **một kiểu thống nhất trong thân phương thức**.
- Vì danh sách có kiểu `List<CAP#1>`, nó chấp nhận phần tử `CAP#1` khi thao tác ghi phù hợp.
- Java không cần biết kiểu thực tế đó là `Integer` hay `String`; các ràng buộc kiểu vẫn đủ để kiểm tra an toàn.

**Capture conversion diễn ra ở compile time.** Nó không thay đổi danh sách ở runtime, không tạo bản sao, không làm mất/đổi kiểu của phần tử và không chuyển `List<Integer>` thành `List<Object>`.

### Quan hệ với các loại wildcard

| Wildcard | Mô hình giới hạn của kiểu capture | Đọc ra an toàn | Thao tác ghi không-null được bảo đảm |
| --- | --- | --- | --- |
| `?` | Một kiểu ẩn có giới hạn trên mặc định `Object` | `Object` | Không có kiểu cụ thể nào thông qua tham chiếu wildcard |
| `? extends Number` | Một kiểu ẩn nằm dưới giới hạn trên `Number` | `Number` | Không có kiểu cụ thể nào thông qua tham chiếu wildcard |
| `? super Integer` | Một kiểu ẩn có giới hạn dưới `Integer`; với `List<E>` giới hạn trên thường là `Object` | `Object` | `Integer` |
| `T` trong `List<T>` | Biến kiểu được đặt tên, có thể dùng lại trong chữ ký/thân phương thức | `T` | `T` |

Đây là mô hình giải thích các trường hợp thông dụng. Quy tắc chính xác về giới hạn còn phụ thuộc ràng buộc của tham số kiểu generic gốc theo Java Language Specification; không nên xem `CAP#1` là một kiểu Java có thể viết trong source code.

## 3. Một wildcard không cho phép tự ý ghi phần tử

Ví dụ phương thức sau cố thêm phần tử vào danh sách bất kỳ:

```java
static void addValue(List<?> items) {
    // items.add("Java"); // LỖI BIÊN DỊCH.
}
```

Nếu `items` là `List<Integer>`, thêm `String` sẽ vi phạm hợp đồng kiểu. Capture conversion **không** hợp pháp hóa câu lệnh này.

Có thể gọi `items.add(null)` xét riêng về kiểm tra kiểu vì `null` tương thích với mọi kiểu tham chiếu. Dù vậy, một danh sách như `List.of(...)` không hỗ trợ chỉnh sửa, và một số implementation có thể không chấp nhận `null`. Phải phân biệt **hợp lệ về kiểu** với **khả năng thao tác lúc chạy**.

`List<?>` đọc ra được `Object`, nhưng không có nghĩa collection này thực sự là `List<Object>`:

```java
List<String> names = new ArrayList<>();
List<?> unknown = names;    // Hợp lệ.
// List<Object> objects = names; // LỖI BIÊN DỊCH.
```

Generics của Java là **bất biến**. Nếu `List<String>` được gán thành `List<Object>`, một đoạn mã có thể chèn một `Integer` vào danh sách chỉ hứa chứa `String`. Wildcard và capture giữ an toàn kiểu mà không phải phá bỏ quy tắc đó.

## 4. Lỗi “capture of ?” xuất hiện từ đâu?

Một ví dụ tiêu biểu:

```java
static void replaceWithItself(List<?> list) {
    list.set(0, list.get(0)); // LỖI BIÊN DỊCH.
}
```

Đây là **đoạn mã cố tình không biên dịch**. Khi biên dịch, `javac` có thể nhắc đến một hoặc nhiều kiểu `capture#... of ?` hay thông báo `Object cannot be converted to capture#...`. Nội dung và số thứ tự cụ thể của thông báo phụ thuộc trình biên dịch.

Tham số đầu vào được khai báo `List<?>`. Lời gọi `set(int, E)` cần một phần tử đúng kiểu `E` của danh sách. Biểu thức `get` sử dụng một lần kiểm tra kiểu/capture, trong khi vị trí tham số của `set` có thể dùng một capture khác. Trình biên dịch không có một **biến kiểu được đặt tên** nối hai thao tác đó trong một hợp đồng generic ổn định.

Vì vậy, thông báo “capture of ?” thường biểu thị: **trình biên dịch đã mở wildcard thành một kiểu ẩn nhưng các ràng buộc hiện có không đủ để chứng minh phép gán hoặc lời gọi là an toàn**.

Phải phân biệt:

- **Lỗi biểu diễn kiểu:** thao tác vốn có thể an toàn (như hoán đổi phần tử trong cùng danh sách), nhưng chữ ký chỉ dùng wildcard nên thiếu quan hệ kiểu rõ ràng.
- **Lỗi thiết kế thật:** thao tác đưa phần tử từ `List<String>` sang `List<Integer>` mà không có quan hệ tương thích. Không có capture helper nào biến việc ghi sai kiểu thành đúng.

## 5. Generic helper “đặt tên” một kiểu đã có thật

Giả sử API ngoài cần nhận mọi danh sách:

```java
static void preserveFirst(List<?> values) {
    preserveCaptured(values);
}

private static <E> void preserveCaptured(List<E> values) {
    if (!values.isEmpty()) {
        E first = values.get(0);
        values.set(0, first);
    }
}
```

Đây là **các method minh họa** cần nằm trong class có import `java.util.List`. Bên ngoài, `?` không chỉ ra tên element type. Khi truyền `values` vào helper, compiler capture wildcard và suy luận một `E` phù hợp; `get` lẫn `set` bên trong cùng dùng `E`. Không có raw type hay unchecked cast.

Ví dụ chỉ ghi lại giá trị cũ để cô lập cơ chế: **kiểu phần tử không cần biết tên nhưng phải nhất quán trong một lời gọi helper**. Nếu list không hỗ trợ `set`, chương trình vẫn có thể ném `UnsupportedOperationException`. Các biến thể ứng dụng như swap, nhân bản phần tử hoặc thao tác với bounds cần xét thêm index, mutability và ranh giới kiểu; capture không cho ghi một giá trị bên ngoài tùy ý.

## 6. Khi nào cần helper, khi nào không?

Không phải mọi phép đọc `List<?>` đều cần capture helper.

Đọc bình thường:

```java
static void show(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Mã này hợp lệ vì đầu ra của `get` hoặc vòng lặp có thể xem như `Object`.

Một generic method một tham số cũng có thể nhận `List<?>`:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

static void printFirst(List<?> unknown) {
    Object firstValue = first(unknown);
    System.out.println(firstValue);
}
```

Ở lời gọi `first(unknown)`, compiler có thể capture wildcard để tìm một `T` thích hợp. Kiểu giá trị trả về được người gọi dùng an toàn dưới dạng `Object`. Phương thức `first` không cần biết `T` cụ thể và không thêm phần tử sai kiểu.

**Cần generic helper nhất khi nhiều thao tác nội bộ phải dùng lại cùng kiểu ẩn**, chẳng hạn vừa đọc vừa ghi lại phần tử trong một collection. Nếu chỉ duyệt và gọi `toString()`, `size()` hoặc `contains(Object)`, thêm helper có thể làm mã phức tạp không cần thiết.

## 7. Hai wildcard có thể là hai kiểu khác nhau

Đây là giới hạn rất quan trọng của capture conversion:

```java
static <T> void requireSameType(List<T> left, List<T> right) {
    // Cả hai tham số phải khớp cùng một T.
}

static void cannotProveSame(List<?> first, List<?> second) {
    requireSameType(first, second); // LỖI BIÊN DỊCH.
}
```

`first` có thể là `List<Integer>`, còn `second` có thể là `List<String>`. Từng `?` có thể tạo một capture khác nhau. Không thể suy ra `T` duy nhất đáp ứng cả hai tham số `List<T>`.

Đặc biệt, **ngay cả truyền cùng một biến hai lần cũng có thể bị từ chối**:

```java
static void stillCannotProveSame(List<?> items) {
    requireSameType(items, items); // LỖI BIÊN DỊCH.
}
```

Hai lần biểu thức `items` được dùng tại hai vị trí đối số có thể trải qua capture conversion riêng biệt. Hệ kiểu không tự chứng minh hai capture là **một kiểu được đặt tên chung**, dù con người biết cùng một object được truyền hai lần.

Ngược lại:

```java
static void worksWithKnownType(List<Integer> items) {
    requireSameType(items, items); // Hợp lệ: T = Integer.
}
```

Ở đây tham số kiểu `Integer` đã được biết từ chữ ký. Nếu API thực sự yêu cầu nhiều tham số cùng một kiểu, hãy truyền thông tin ấy qua biến kiểu generic `<T>` ngay từ chữ ký phù hợp, thay vì xóa thành các `List<?>` độc lập.

### Vì sao helper một tham số hoạt động nhưng helper hai tham số thất bại?

- `swapCaptured(List<T>)` cần **một kiểu ẩn** để đọc và ghi trong cùng một danh sách. Một capture có thể được suy luận thành `T`.
- `requireSameType(List<T>, List<T>)` yêu cầu **hai đối số** có cùng `T`. Từ hai lần sử dụng `List<?>`, trình biên dịch không thể cam kết hai capture là một.

Đó là ranh giới giữa **đặt tên kiểu chưa biết** và **tự tạo ra quan hệ kiểu không có trong chữ ký**.

## 8. Capture conversion với wildcard có giới hạn

Cơ chế capture cũng liên quan đến `? extends T` và `? super T`, không chỉ `?`.

### `? extends Number`: đọc số như `Number`

```java
static double sum(List<? extends Number> source) {
    double result = 0.0;
    for (Number n : source) {
        result += n.doubleValue();
    }
    return result;
}
```

Kiểu phần tử ẩn thỏa giới hạn trên `Number`. Nhờ đó đọc ra như `Number` an toàn, nhưng không được thêm một `Integer` cụ thể vào `source`: nguồn có thể thật sự là `List<Double>`.

Ví dụ phần tử từ chính danh sách có thể được ghi trở lại bằng helper:

```java
static void repeatFirst(List<? extends Number> source) {
    repeatCaptured(source);
}

private static <T extends Number> void repeatCaptured(List<T> source) {
    if (!source.isEmpty()) {
        T value = source.get(0);
        source.add(value);
    }
}
```

Thao tác này chỉ đưa **đúng một phần tử kiểu `T` đang có** vào cùng `List<T>`. Nó an toàn về kiểu, nhưng collection phải hỗ trợ thêm phần tử; nếu là `List.of(1, 2)`, thao tác sẽ ném `UnsupportedOperationException`.

### `? super Integer`: ghi `Integer` vào đích

```java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);

    Object any = target.get(0);  // Chỉ bảo đảm đọc dưới dạng Object.
    System.out.println(any);
}
```

Với kiểu lower-bounded, đối số kiểu thật có thể là `Integer`, `Number` hoặc `Object`. Đích chắc chắn nhận được `Integer`, nhưng các phần tử hiện có không nhất thiết là `Integer`.

**Capture không làm thay đổi quyền đọc/ghi an toàn do bounds quyết định.** Nó không thể biến `List<? extends Number>` thành đích nhận mọi `Number`, hay biến `List<? super Integer>` thành nguồn chắc chắn chỉ chứa `Integer`.

## 9. Khi cần chuyển phần tử giữa hai danh sách: mô tả quan hệ kiểu

Một helper một tham số giải quyết việc đọc/ghi trong **cùng danh sách**. Nếu muốn **chuyển phần tử giữa hai danh sách khác nhau**, hãy mô tả rõ ràng quan hệ nguồn–đích:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
```

`source` là producer, có thể cung cấp các phần tử dùng như `T`; `destination` là consumer, chấp nhận `T`.

Ví dụ:

```java
List<Integer> integers = List.of(3, 5);
List<Number> numbers = new ArrayList<>();

appendAll(integers, numbers); // Hợp lệ: Integer là Number.
```

Một hàm nhận tùy ý hai `List<?>` không thể có cùng hợp đồng:

```java
static void unsafeAttempt(List<?> destination, List<?> source) {
    // destination.add(source.get(0)); // LỖI BIÊN DỊCH.
}
```

Lý do không phải thiếu thủ thuật capture. Hai danh sách có thể chứa kiểu không liên quan (`String` và `Integer`); API phải thể hiện **quan hệ tương thích thật** nếu muốn chuyển phần tử.

Có thể gọi `appendAll` giữa các danh sách có quan hệ hợp lệ; nhưng không nên cho phép source và destination là cùng một danh sách có thể thay đổi trong lúc duyệt mà không xử lý trường hợp đó. Với `ArrayList`, vừa duyệt vừa thêm thường gây `ConcurrentModificationException`. Khi thiết kế API, có thể quy định hai đối số không được trùng nhau hoặc lấy snapshot phù hợp trước khi thao tác.

## 10. Ví dụ Java 17+ hoàn chỉnh

Chương trình dưới đây minh họa năm ý:

1. `List<?>` nhận danh sách có những kiểu phần tử khác nhau.
2. Phương thức generic một tham số đọc được từ `List<?>` nhờ capture conversion.
3. Helper `<T>` hoán đổi và sao chép phần tử **trong chính danh sách**.
4. Hai danh sách không có kiểu phần tử giống nhau vẫn được xử lý riêng mà không ép kiểu.
5. Khi cần chuyển phần tử giữa danh sách nguồn và đích, API dùng `extends/super` để biểu diễn quan hệ kiểu.

Lưu thành tệp **`CaptureConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureConversionDemo {
    static Object first(List<?> items) {
        return items.get(0);
    }

    static void swap(List<?> items, int a, int b) {
        swapCaptured(items, a, b);
    }

    private static <T> void swapCaptured(List<T> items, int a, int b) {
        T saved = items.get(a);
        items.set(a, items.get(b));
        items.set(b, saved);
    }

    static void duplicateFirst(List<?> items) {
        duplicateCaptured(items);
    }

    private static <T> void duplicateCaptured(List<T> items) {
        if (!items.isEmpty()) {
            items.add(items.get(0));
        }
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> ids = new ArrayList<>(List.of(7, 8, 9));
        List<String> tags = new ArrayList<>(List.of("core", "java"));

        List<?> hiddenIds = ids;
        List<?> hiddenTags = tags;

        System.out.println("first ids = " + first(hiddenIds));
        System.out.println("first tags = " + first(hiddenTags));

        swap(hiddenIds, 0, 2);
        swap(hiddenTags, 0, 1);
        duplicateFirst(hiddenIds);

        System.out.println("ids = " + ids);
        System.out.println("tags = " + tags);

        List<Number> destination = new ArrayList<>();
        appendAll(ids, destination);
        System.out.println("destination = " + destination);
    }
}
```

Biên dịch/chạy:

```bash
javac CaptureConversionDemo.java
java CaptureConversionDemo
```

Stdout:

```text
first ids = 7
first tags = core
ids = [9, 8, 7, 9]
tags = [java, core]
destination = [9, 8, 7, 9]
```

Giải thích:

- `hiddenIds` trỏ tới `List<Integer>` và `hiddenTags` trỏ tới `List<String>`; cả hai đều dùng được với `List<?>`.
- `first` chỉ lấy giá trị như `Object` nên không cần quyền ghi.
- `swapCaptured` giữ một `T` cho từng lời gọi, nên `Integer` chỉ được hoán đổi với `Integer` và `String` chỉ với `String`.
- `duplicateCaptured` lấy phần tử đầu kiểu `T` rồi thêm chính phần tử đó vào `List<T>`. `ids` có thêm `9`, còn `tags` không thay đổi cấu trúc sau `swap`.
- `appendAll` đọc `Integer` từ `ids` rồi đưa vào danh sách đích `List<Number>`. Việc này khác với một phép gán sai kiểu `List<Number> x = ids`.

Chương trình dùng `ArrayList` có thể sửa đổi; nếu thay bằng danh sách được tạo bởi `List.of(...)` ở những chỗ `swap`/`duplicateFirst` thay đổi phần tử, phải xét các ngoại lệ sửa đổi runtime.

## 11. Capture conversion khác gì type inference và type erasure?

Ba khái niệm này có liên quan nhưng không đồng nghĩa.

| Cơ chế | Xảy ra chủ yếu ở đâu? | Mục đích |
| --- | --- | --- |
| **Capture conversion** | Trình biên dịch, khi xử lý kiểu chứa wildcard | Mở `?` thành một biến kiểu ẩn mới với ràng buộc thích hợp |
| **Type inference** | Trình biên dịch, khi suy luận tham số kiểu của lời gọi generic | Tìm `T` phù hợp từ đối số, ràng buộc và ngữ cảnh; có thể làm việc cùng capture |
| **Type erasure** | Quá trình biên dịch sang bytecode | Biểu diễn generic ở runtime chủ yếu qua kiểu xóa và các cast/bridge thích hợp |

Một lời gọi `swapCaptured(items)` với `items` thuộc `List<?>` thường cần cả **capture conversion** (một kiểu ẩn cho dấu `?`) và **type inference** (suy luận `T` trong lời gọi helper). Sau khi biên dịch, việc có một biến kiểu `T` tạm thời không tạo ra một lớp runtime mới có tên `CAP#...`.

Ví dụ sau **không** dùng capture để kiểm tra phần tử runtime:

```java
// Không hợp lệ: không thể kiểm tra đối số kiểu Integer bằng instanceof.
// if (unknown instanceof List<Integer>) { ... }
```

Tương tự, một unchecked cast có thể làm trình biên dịch bớt cảnh báo, nhưng không chứng minh hai wildcard là cùng kiểu và không khiến thao tác ghi sai kiểu trở nên an toàn.

## 12. Những giới hạn cần nhớ

### Capture conversion không cấp quyền ghi tùy ý

`List<?>` vẫn không chấp nhận thêm `"text"`; `List<? extends Number>` vẫn không chấp nhận thêm `Integer` tùy ý. Capture chỉ cho phép sử dụng **phần tử đã biết là đúng cùng kiểu `T`** thông qua helper thích hợp.

### Capture không thống nhất hai wildcard độc lập

`List<?> a` và `List<?> b` có thể ứng với hai kiểu khác nhau. Không thể suy ra các phần tử trao đổi được chỉ vì cả hai biến có cùng dạng `List<?>`.

### Capture không khôi phục đối số generic ở runtime

Type erasure vẫn áp dụng. Không có thao tác runtime tự động “đọc được kiểu thật của `List<?>`” từ capture conversion.

### Capture không loại bỏ lỗi runtime khác

Một generic helper an toàn về kiểu vẫn có thể ném `IndexOutOfBoundsException` do chỉ số sai, `UnsupportedOperationException` khi danh sách không sửa được, hoặc `NullPointerException` nếu dùng tham chiếu `null` mà không kiểm tra.

### Capture không thay thế thiết kế chữ ký API

Nếu phương thức cần thêm số vào đích, dùng `Collection<? super Integer>` hoặc `Collection<? super T>`. Nếu chỉ lấy số từ nguồn, dùng `Collection<? extends Number>`. Nếu cần ràng buộc nhiều đối số, sử dụng biến kiểu `<T>` thể hiện quan hệ đó. Chỉ dùng capture helper khi một thao tác bên trong thật sự cần đặt tên cho **một kiểu ẩn đã có**.

## 13. Quy trình xử lý lỗi “capture#... of ?”

Khi gặp lỗi biên dịch đề cập `capture of ?`, hãy kiểm tra theo thứ tự:

1. **Tham số nào chứa wildcard?** Ví dụ `List<?>`, `List<? extends Number>` hay `List<? super Integer>`.
2. **Thao tác muốn đọc hay ghi?** Đọc dưới dạng giới hạn trên thường hợp lệ; ghi phải tương thích với kiểu ẩn cụ thể.
3. **Giá trị ghi có xuất phát từ chính đối tượng đó không?** Nếu đọc từ cùng một danh sách rồi dùng lại, một generic helper `<T>` nhận **một `List<T>`** có thể diễn đạt quan hệ an toàn.
4. **Có hai danh sách/wildcard khác nhau không?** Nếu có, không được tự coi chúng cùng kiểu; phải thể hiện quan hệ nguồn–đích hoặc dùng kiểu xác định hơn.
5. **Có đang cố ép kiểu hoặc dùng raw type để lách compiler không?** Hãy sửa chữ ký, loại bỏ cast không kiểm tra và để compiler chứng minh quan hệ trước khi ghi.
6. **Giải pháp có còn hợp đồng runtime không?** Chỉ số hợp lệ, collection mutable và điều kiện aliasing vẫn cần được bảo đảm.

Ví dụ sửa nhanh:

```java
// Sai: không có tên kiểu chung để vừa get vừa set.
// static void wrong(List<?> x) {
//     x.set(0, x.get(0));
// }

// Đúng: helper giữ nhất quán T ở bên trong.
static void right(List<?> x) {
    rightCaptured(x);
}

private static <T> void rightCaptured(List<T> x) {
    if (!x.isEmpty()) {
        T value = x.get(0);
        x.set(0, value);
    }
}
```

Các phương thức `right`/`rightCaptured` là đoạn code minh họa để đặt trong một lớp; dòng `wrong` đã comment nhằm chỉ ra lỗi biên dịch. Khi sử dụng, cần import `java.util.List`.

## 14. Bài tập tự kiểm tra

Giả sử đã có:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<String> words = new ArrayList<>(List.of("a", "b"));
List<?> a = ints;
List<?> b = words;
```

Đánh giá những câu sau:

| Biểu thức/thao tác | Kết quả | Lý do |
| --- | --- | --- |
| `Object x = a.get(0);` | Hợp lệ | Đọc `List<?>` ra `Object` |
| `a.add(3);` | Lỗi biên dịch | Kiểu phần tử cụ thể chưa biết |
| `a.set(0, a.get(0));` | Lỗi biên dịch | Thiếu một `T` thống nhất giữa hai thao tác qua wildcard |
| `swap(a, 0, 1);` với helper ở phần 10 | Hợp lệ | Java capture một kiểu ẩn cho lời gọi helper |
| `swap(b, 0, 1);` | Hợp lệ | Một capture khác, áp dụng cho danh sách `String` |
| `requireSameType(a, b);` với `<T> void requireSameType(List<T>, List<T>)` | Lỗi biên dịch | Hai capture không có quan hệ bằng nhau |
| `a.add(null);` | Hợp lệ về kiểu | Nhưng còn phụ thuộc việc collection hỗ trợ ghi/null |
| `Object first = first(a);` với `first(List<?>)` ở phần 10 | Hợp lệ | Đọc như `Object` |
| `appendAll(ints, new ArrayList<Number>());` | Hợp lệ | Nguồn `Integer` và đích `Number` tương thích |

Các phép gọi cần phần tử hoặc vị trí hợp lệ đều có thể gặp ngoại lệ nếu collection rỗng; bảng chỉ xét **tính hợp lệ kiểu của Java**.

## Ghi nhớ

- **Capture conversion** “mở” một wildcard thành **kiểu ẩn có giới hạn** để trình biên dịch kiểm tra các phép dùng generic một cách nhất quán.
- Với `List<?>`, ta có thể đọc như `Object` nhưng không thể tự thêm một phần tử không-null tùy ý.
- `list.set(0, list.get(0))` trên `List<?>` thường bị từ chối do thiếu một quan hệ kiểu được đặt tên chung; **generic helper `<T>`** giải quyết trường hợp an toàn này bằng cách nhận một `List<T>`.
- **Một wildcard không tự bằng wildcard khác.** Hai lần dùng `List<?>` có thể tạo capture độc lập, kể cả khi truyền cùng một biến vào hai đối số.
- Capture không thể làm hợp lệ một phép chuyển `String` vào `List<Integer>`, không loại bỏ tính bất biến của Java Generics và không thay đổi kiểu ở runtime.
- Nếu API thật sự liên hệ hai tham số, hãy dùng `<T>` với các giới hạn `? extends T` cho nguồn và `? super T` cho đích để biểu diễn quan hệ an toàn.
- Khi thấy lỗi `capture#... of ?`, kiểm tra **bạn đang cần một kiểu ẩn thống nhất trong cùng collection**, hay đang giả định sai rằng hai kiểu ẩn độc lập là như nhau.

Hiểu capture conversion giúp viết phương thức nhận wildcard linh hoạt mà vẫn thao tác đúng kiểu với dữ liệu, đồng thời phân biệt được những lỗi có thể giải quyết bằng generic helper và những lỗi cần thay đổi hợp đồng API.
