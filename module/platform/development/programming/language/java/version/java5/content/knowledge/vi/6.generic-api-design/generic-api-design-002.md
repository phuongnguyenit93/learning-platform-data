# Thiết kế lớp chứa dữ liệu generic

## 1. Lớp generic phải giữ một quan hệ kiểu có ích

Một lớp chứa dữ liệu generic mô tả một cấu trúc có thể dùng với nhiều kiểu phần tử, trong khi vẫn giữ mối liên hệ giữa:

- Kiểu dữ liệu được đưa vào.
- Kiểu được lưu trong trạng thái nội bộ.
- Kiểu dữ liệu được lấy ra.

Ví dụ, `Box<String>` nhận và trả chuỗi; `Box<Integer>` nhận và trả số nguyên. Người gọi không cần lấy `Object` rồi ép kiểu mỗi lần đọc.

Mục tiêu không phải là thay mọi kiểu cụ thể bằng chữ `T`. Một tham số kiểu có giá trị khi nó giúp **giữ cùng một hợp đồng kiểu qua nhiều vị trí của API và trạng thái**.

Nếu lớp chỉ nhận một giá trị để gọi `toString()` rồi không lưu hoặc liên kết kiểu với kết quả nào, có thể không cần biến cả lớp thành generic. Ngược lại, một lớp chứa giữ phần tử lâu dài thường cần tham số kiểu ở cấp lớp.

Bài xây dựng một lớp chứa nhiều phần tử có tên `Batch<E>`. Ví dụ chạy trên Java 17 trở lên và dùng những khả năng vẫn áp dụng trong Java hiện nay.

## 2. Bắt đầu từ hợp đồng dữ liệu, không bắt đầu từ cú pháp <T>

Trước khi viết lớp, quyết định các quy tắc:

| Câu hỏi | Quyết định cho Batch<E> trong bài |
| --- | --- |
| Chứa một hay nhiều phần tử? | Nhiều phần tử theo thứ tự |
| Có cho phép trùng phần tử? | Có |
| Có cho phép `null`? | Không |
| Có thể rỗng? | Có |
| Có thể thay đổi sau khi tạo? | Có, qua các phương thức của lớp |
| Có giữ nguyên danh sách nguồn? | Không; sao chép cấu trúc đầu vào |
| Người gọi có được sửa trực tiếp danh sách bên trong? | Không |
| Lấy ảnh chụp dữ liệu ra ngoài bằng cách nào? | Trả `List<E>` không cho sửa, tách khỏi các thay đổi cấu trúc về sau |
| Có tự bảo đảm an toàn luồng? | Không |

Các quyết định này không tự đến từ cú pháp generic. `Batch<E>` cho biết quan hệ kiểu phần tử, nhưng không cho biết lớp có cho `null`, có thể thay đổi hay có an toàn khi nhiều luồng dùng chung hay không.

Một API tốt cần diễn đạt cả hai nhóm thông tin: **quan hệ kiểu** trong chữ ký và **hợp đồng hành vi** trong thiết kế, mã kiểm tra cùng tài liệu.

## 3. Đặt tham số kiểu ở đúng phạm vi

### 3.1. Kiểu dữ liệu của trạng thái thuộc về lớp

Một lớp chứa một giá trị có thể có hình dạng:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = java.util.Objects.requireNonNull(value, "value");
    }

    T get() {
        return value;
    }
}
```

Đây là lớp minh họa độc lập, không phải chương trình có `main`.

`T` xuất hiện ở trường dữ liệu, constructor và kết quả trả về. Cùng một `T` liên kết ba vị trí đó.

Với `Box<String>`:

```java
Box<String> name = new Box<>("An");
String value = name.get();
```

Không cần ép kiểu ở phía người gọi. Nếu viết một lớp chỉ dùng `Object` cho cả trường và kết quả, trình biên dịch không còn giữ mối quan hệ cụ thể này cho người sử dụng.

### 3.2. Đừng tạo một tham số kiểu mới che khuất kiểu của lớp

Thiết kế dưới đây không diễn tả một setter đúng cho trạng thái `T`:

```java
class ConfusingBox<T> {
    private T value;

    public <T> void set(T input) {
        // value = input; // Khong the coi hai T nay la cung mot kieu
    }
}
```

`T` của phương thức là một tham số kiểu mới, che khuất tên `T` của lớp. Nó không có quan hệ bảo đảm với kiểu trường `value`.

Nếu muốn setter nhận đúng kiểu của lớp, chữ ký phải là:

```java
public void set(T input)
```

Đây là chữ ký minh họa. Chỉ tạo tham số kiểu cấp phương thức khi phương thức cần một quan hệ mới, chẳng hạn `<R> Batch<R> map(...)`.

### 3.3. Thành viên static không thuộc riêng một đối số kiểu

Một trường `static` được chia sẻ ở mức lớp, không có một bản riêng cho `Batch<String>` và một bản khác cho `Batch<Integer>`.

Vì vậy, không thể dùng tham số kiểu của lớp làm kiểu trường `static`:

```java
class WrongStatic<T> {
    // private static T cached; // Khong bien dich
}
```

Một factory `static` có thể khai báo **tham số kiểu của riêng nó**:

```java
public static <T> Batch<T> empty()
```

`T` ở đây thuộc lời gọi factory. Nó không lấy từ một đối tượng `Batch` đã tồn tại. Quy tắc phạm vi của tham số kiểu lớp được mô tả trong [JLS: Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.2).

## 4. Kiểu nội bộ nên chính xác; wildcard nên thể hiện vai trò ở biên

Với lớp `Batch<E>`, trạng thái được lưu bằng:

```java
private final List<E> items;
```

Ta biết phần tử thuộc kiểu `E`. Dùng `List<E>` giúp lớp đọc và ghi nhất quán.

Nếu khai báo trường là `List<? extends E>`, lớp không thể thêm một `E` tùy ý vì kiểu phần tử thực tế có thể là một kiểu con chưa biết. Nếu khai báo `List<? super E>`, đọc tổng quát chỉ bảo đảm `Object`, không giữ được API trả `E` một cách đơn giản.

Do đó:

- Dùng kiểu chính xác `E` cho dữ liệu do lớp sở hữu.
- Dùng wildcard ở tham số để mô tả nguồn cung cấp hoặc nơi tiếp nhận dữ liệu khi cần linh hoạt.

### Nguồn đưa phần tử vào lớp

```java
void addAll(Collection<? extends E> source)
```

`source` cung cấp phần tử có thể nhìn như `E`. Ví dụ, một `Batch<Number>` có thể nhận nguồn `List<Integer>` hoặc `List<Double>`.

### Đích nhận phần tử của lớp

```java
void copyTo(Collection<? super E> destination)
```

`destination` phải nhận được `E`. Một `Batch<Integer>` có thể sao chép phần tử ra `List<Integer>`, `List<Number>` hoặc `List<Object>`.

Các chữ ký trên là những mảnh API minh họa, có triển khai đầy đủ ở phần sau.

### Kết quả đọc thông thường giữ E

```java
E get(int index)
List<E> snapshot()
```

Khi lớp biết chính xác quan hệ kiểu, không cần ép người gọi xử lý `? extends E` ở mọi kết quả trả về. Wildcard không phải dấu hiệu “generic hơn thì tốt hơn”; hãy dùng nó cho một yêu cầu linh hoạt cụ thể.

## 5. Bảo vệ quyền sở hữu dữ liệu

### 5.1. Sao chép đầu vào

Nếu constructor chỉ gán:

```java
// this.items = source;
```

thì người giữ `source` có thể sửa dữ liệu của lớp từ bên ngoài. Một đường sửa như vậy có thể đi vòng qua kiểm tra `null` và các quy tắc nghiệp vụ.

Lớp trong bài nhận `Collection<? extends E>` rồi tạo `ArrayList<E>` riêng. Cấu trúc dữ liệu thuộc về `Batch`, còn nguồn tiếp tục thuộc về người gọi.

### 5.2. Không trả trực tiếp danh sách nội bộ

Một getter như `return items;` sẽ cho phép người gọi thêm, xóa hoặc đặt `null` mà không qua các phương thức của lớp.

Ta dùng `List.copyOf(items)` để trả một ảnh chụp (snapshot) không cho sửa cấu trúc. Ảnh chụp cũ không tự thay đổi khi `Batch` thêm phần tử mới.

Đây là hợp đồng của [List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

### 5.3. Snapshot không đồng nghĩa sao chép sâu

Nếu `E` là một đối tượng có trạng thái có thể sửa, cả lớp chứa và snapshot vẫn có thể giữ tham chiếu tới cùng đối tượng phần tử.

Ví dụ, với `Batch<StringBuilder>`, việc sửa nội dung một `StringBuilder` vẫn có thể được quan sát qua mọi nơi đang giữ tham chiếu tới nó.

Generic không biết cách sao chép sâu mọi kiểu `E`. Nếu cần bất biến sâu, phải dùng phần tử bất biến, nhận một chiến lược sao chép hoặc định nghĩa hợp đồng riêng phù hợp miền dữ liệu.

### 5.4. final chỉ giữ ổn định tham chiếu

`private final List<E> items` không ngăn `items.add(...)`. Nó ngăn trường `items` được gán lại sau khởi tạo; danh sách mà trường trỏ tới vẫn có thể thay đổi.

Lớp trong bài là lớp chứa có thể thay đổi, với các đường thay đổi được kiểm soát. Không gọi nó là bất biến chỉ vì trường mang từ khóa `final`.

## 6. Chính sách rỗng và null phải nhất quán

`Batch` có thể rỗng nhưng không chứa `null`. Vì vậy:

- Factory với nguồn rỗng tạo một `Batch` rỗng.
- `add(null)` bị từ chối.
- Nguồn của `addAll` có bất kỳ phần tử `null` nào bị từ chối.
- Kết quả `map` cũng không được chứa `null`.
- `first()` trả `Optional.empty()` khi không có phần tử.

`Optional<E>` ở đây dùng làm kiểu trả về để biểu diễn “không có kết quả đầu tiên” rõ ràng. Không trả chính biến `Optional` là `null`. Vai trò này phù hợp với [API Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html).

Một thiết kế khác có thể cho phép `null`, nhưng lúc đó `Optional.empty()` không phân biệt được “không có phần tử” và “phần tử đầu là null” nếu không có thêm quy ước. Quyết định cho `null` phải được đặt trước cách thiết kế phương thức truy xuất.

Đối với `get(index)`, lớp giữ hành vi chỉ số của `List`: chỉ số ngoài phạm vi gây `IndexOutOfBoundsException`. Không dùng `null` làm giá trị đánh dấu cho cả “không tồn tại” lẫn “lỗi chỉ số”.

## 7. Chương trình đầy đủ: Batch<E> có hợp đồng rõ ràng

Lưu thành `GenericContainerDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

public class GenericContainerDemo {
    static final class Batch<E> {
        private final List<E> items;

        private Batch(Collection<? extends E> source) {
            this.items = validatedCopy(source);
        }

        public static <T> Batch<T> from(Collection<? extends T> source) {
            return new Batch<>(source);
        }

        public static <T> Batch<T> empty() {
            return new Batch<>(List.of());
        }

        private static <T> List<T> validatedCopy(
                Collection<? extends T> source) {
            Objects.requireNonNull(source, "source");
            List<T> copy = new ArrayList<>();
            for (T value : source) {
                copy.add(Objects.requireNonNull(value, "item"));
            }
            return copy;
        }

        public void add(E value) {
            items.add(Objects.requireNonNull(value, "item"));
        }

        public void addAll(Collection<? extends E> source) {
            List<E> incoming = validatedCopy(source);
            items.addAll(incoming);
        }

        public E get(int index) {
            return items.get(index);
        }

        public int size() {
            return items.size();
        }

        public Optional<E> first() {
            return items.isEmpty()
                    ? Optional.empty()
                    : Optional.of(items.get(0));
        }

        public List<E> snapshot() {
            return List.copyOf(items);
        }

        public void copyTo(Collection<? super E> destination) {
            Objects.requireNonNull(destination, "destination");
            destination.addAll(items);
        }

        public <R> Batch<R> map(Function<? super E, ? extends R> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            List<R> mapped = new ArrayList<>();
            for (E value : items) {
                R result = Objects.requireNonNull(
                        mapper.apply(value), "mapped item");
                mapped.add(result);
            }
            return Batch.from(mapped);
        }
    }

    public static void main(String[] args) {
        Batch<Integer> integers = Batch.from(List.of(1, 2, 3));
        Batch<Number> numbers = Batch.from(integers.snapshot());
        numbers.add(2.5);
        System.out.println("numbers = " + numbers.snapshot());

        List<Object> destination = new ArrayList<>();
        integers.copyTo(destination);
        System.out.println("destination = " + destination);

        Batch<String> labels = integers.map(value -> "item-" + value);
        System.out.println("labels = " + labels.snapshot());

        List<String> source = new ArrayList<>(List.of("An"));
        Batch<String> names = Batch.from(source);
        source.add("Binh");
        List<String> before = names.snapshot();
        names.add("Chi");
        System.out.println("source = " + source);
        System.out.println("old snapshot = " + before);
        System.out.println("names = " + names.snapshot());

        Batch<String> empty = Batch.empty();
        System.out.println("empty first = " + empty.first().orElse("none"));
        System.out.println("first name = " + names.first().orElse("none"));

        try {
            numbers.addAll(Arrays.asList(10, null, 20));
        } catch (NullPointerException exception) {
            System.out.println("null rejected before batch update");
        }
        System.out.println("numbers after rejection = " + numbers.snapshot());

        try {
            names.snapshot().add("Dung");
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot cannot be modified");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all -Werror GenericContainerDemo.java
java GenericContainerDemo
```

Stdout:

```text
numbers = [1, 2, 3, 2.5]
destination = [1, 2, 3]
labels = [item-1, item-2, item-3]
source = [An, Binh]
old snapshot = [An]
names = [An, Chi]
empty first = none
first name = An
null rejected before batch update
numbers after rejection = [1, 2, 3, 2.5]
snapshot cannot be modified
```

`Batch` được đặt thành lớp lồng nhau `static` để toàn bộ ví dụ nằm trong một tệp chạy được. Trong thư viện thực tế, có thể tách nó thành lớp ở tệp riêng và điều chỉnh quyền truy cập theo API cần công bố.

## 8. Đọc thiết kế qua những hành vi đã kiểm chứng

### 8.1. Mở rộng kiểu bằng cách tạo container mới

Chương trình tạo `Batch<Number>` từ snapshot của `Batch<Integer>`:

```java
Batch<Number> numbers = Batch.from(integers.snapshot());
```

Đây là một đối tượng container mới, có vùng lưu trữ riêng và hợp đồng phần tử `Number`. Nó có thể thêm `Double` như `2.5` mà không làm hỏng `Batch<Integer>` ban đầu.

Không được thay bằng phép gán:

```java
// Batch<Number> numbers = integers; // Khong bien dich
```

Các kiểu generic thông thường là bất biến theo đối số kiểu. Nếu được gán thẳng, một tham chiếu `Batch<Number>` có thể đưa `Double` vào chính đối tượng mà tham chiếu kia tin là `Batch<Integer>`.

### 8.2. Factory generic khai báo quan hệ riêng

Factory:

```java
public static <T> Batch<T> from(Collection<? extends T> source)
```

liên kết kiểu phần tử nguồn với kiểu của container mới. Dựa vào kiểu đích `Batch<Number>` và nguồn số nguyên, trình biên dịch có thể suy luận `T = Number` phù hợp.

Với factory rỗng:

```java
Batch<String> names = Batch.empty();
```

kiểu đích cung cấp thông tin `T = String`. Nếu một lời gọi không có đủ ngữ cảnh, có thể ghi tham số kiểu tường minh như `Batch.<String>empty()`.

### 8.3. map tạo một quan hệ kiểu mới

```java
public <R> Batch<R> map(Function<? super E, ? extends R> mapper)
```

`E` thuộc container hiện tại, còn `R` là kiểu kết quả của lần gọi phương thức.

Hàm chuyển đổi nhận được một `E` và cung cấp một giá trị phù hợp với `R`. Vì vậy:

- Đầu vào hàm dùng `? super E`.
- Đầu ra hàm dùng `? extends R`.
- Container kết quả là `Batch<R>`.

`map` không đổi container hiện tại thành container của kiểu mới. Nó tạo container khác, nhờ đó không vi phạm hợp đồng `E` đã tồn tại.

Nếu hàm chuyển đổi trả `null`, ví dụ từ chối bằng `NullPointerException` theo chính sách không chứa `null`. Nếu hàm tự ném ngoại lệ, ngoại lệ được truyền ra ngoài. Hàm chuyển đổi không được sửa chính `Batch` nguồn trong lúc duyệt. Lớp không hoàn tác những tác dụng phụ do hàm này tạo ra.

Đây là quan hệ đầu vào và kết quả của một [Function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html), không phải cơ chế ép kiểu các phần tử cũ.

### 8.4. addAll kiểm tra trước khi thay đổi trạng thái

`validatedCopy` tạo một danh sách trung gian và kiểm tra toàn bộ nguồn trước. Chỉ khi nguồn hợp lệ, `items.addAll(incoming)` mới được gọi.

Do đó, nguồn `[10, null, 20]` trong chương trình bị từ chối mà không thêm trước số `10` vào container.

Phạm vi bảo đảm là việc từ chối `null` xảy ra trước thay đổi cấu trúc của `Batch`. Không suy rộng thành một giao dịch có thể hoàn tác mọi lỗi bộ nhớ hoặc mọi tác dụng phụ của đối tượng nguồn tùy biến.

### 8.5. copyTo không sở hữu đích

`copyTo` không sửa container nguồn. Tuy nhiên, đích có thể:

- Không hỗ trợ thêm phần tử.
- Có chính sách riêng về dung lượng hoặc nội dung.
- Ném ngoại lệ sau khi đã nhận một phần dữ liệu.

Phương thức không tự cung cấp cơ chế hoàn tác cho một tập hợp đích bất kỳ. Hợp đồng phải nói rõ trách nhiệm này, thay vì cho rằng chữ ký generic đã bảo đảm mọi hành vi lúc chạy.

## 9. Khi nào nên thêm giới hạn cho tham số kiểu?

Không cần `E extends Number` nếu lớp chỉ lưu trữ, duyệt hoặc trả dữ liệu. Giới hạn như vậy sẽ loại bỏ `String` mà không mang lại khả năng cần thiết.

Chỉ thêm giới hạn khi toàn bộ hợp đồng của lớp cần các thao tác đó, chẳng hạn một container chuyên tính toán dựa trên `Number`.

Cũng có thể giữ lớp chứa tổng quát và đưa thuật toán riêng ra ngoài hoặc nhận một hành vi dưới dạng hàm. Ví dụ, chuyển phần tử thành chuỗi qua `Function` không buộc lớp yêu cầu mọi `E` kế thừa một lớp định dạng riêng.

Nếu chỉ một phương thức cần một khả năng bổ sung, cân nhắc liệu khả năng ấy nên được truyền vào hay nằm trong một kiểu lớp chuyên biệt. Không làm mọi người dùng của container gánh một giới hạn chỉ vì một tác vụ cục bộ.

## 10. Những quyết định khác cần công bố khi biến ví dụ thành API

### So sánh bằng giá trị hay bằng danh tính?

Lớp `Batch` trong bài không ghi đè `equals` và `hashCode`, nên hai đối tượng khác nhau không tự được xem là bằng nhau chỉ vì chứa các phần tử giống nhau.

Nếu muốn một kiểu giá trị, cần định nghĩa rõ thứ tự, phần tử trùng, trạng thái có thể thay đổi và tác động khi dùng đối tượng làm khóa của `Map`.

Với một lớp chỉ chứa một hay vài trường dữ liệu và không cần cập nhật, một record generic có thể phù hợp hơn. Nhưng record giữ một danh sách cũng không tự sao chép sâu hay tự làm danh sách đó bất biến; vẫn phải xử lý quyền sở hữu cấu trúc.

### Có cần kế thừa không?

Ví dụ dùng `final` để không mở thêm đường ghi thông qua lớp con. Đây là lựa chọn giữ phạm vi hợp đồng đơn giản.

Nếu định cho kế thừa, cần thiết kế rõ constructor, những phương thức được ghi đè và các quy tắc lớp con phải giữ. Generic không tự giải quyết bài toán bảo toàn hợp đồng khi mở rộng lớp.

### Có cần nhiều luồng dùng chung không?

Các phương thức trong ví dụ không đồng bộ. Việc dùng `List.copyOf` để trả snapshot không làm thao tác lấy snapshot trở nên an toàn khi một luồng khác đồng thời sửa danh sách nội bộ.

Muốn dùng chung giữa luồng, cần thiết kế riêng về khóa, bất biến hoặc cơ chế quản lý trạng thái. Đó là yêu cầu bổ sung, không phải hệ quả của `Batch<E>`.

### Có thực sự cần một lớp chứa mới không?

Nếu lớp chỉ đổi tên `List<E>` mà không thêm quy tắc, có thể dùng `List<E>` trực tiếp.

Lớp riêng hữu ích khi nó giữ một hợp đồng mà tập hợp nền không tự thể hiện: cấm `null` nhất quán, quy tắc cập nhật, giới hạn dung lượng, dữ liệu theo lô hoặc hành vi nghiệp vụ cụ thể. Không tạo một lớp bọc chỉ để tăng số tầng.

## 11. Lỗi thiết kế cần tránh

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Lưu `Object` rồi ép kiểu ở getter | Mất quan hệ kiểu ở API | Dùng tham số kiểu gắn với trạng thái |
| Setter tự khai báo một `<T>` mới | Không còn cùng kiểu với trường của lớp | Dùng kiểu lớp; chỉ đặt kiểu mới khi cần |
| Dùng wildcard cho trạng thái nội bộ dù cần cả đọc và ghi | Gây mất thông tin hoặc chặn thao tác cần thiết | Lưu `List<E>`; đặt wildcard ở biên |
| Giữ trực tiếp danh sách nguồn có thể sửa | Có đường thay đổi đi vòng kiểm tra | Sao chép cấu trúc đầu vào |
| Trả danh sách nội bộ | Người gọi sửa được trạng thái không qua API | Snapshot hoặc cách nhìn có hợp đồng rõ ràng |
| Có lúc cho `null`, có lúc từ chối | Kết quả và lỗi khó dự đoán | Quy định chính sách chung |
| Cho rằng `final` nghĩa là bất biến sâu | Đánh giá sai khả năng thay đổi dữ liệu | Phân biệt tham chiếu, cấu trúc và phần tử |
| Đổi kiểu container bằng ép kiểu unchecked | Có thể phá hợp đồng phần tử | Tạo container mới với kiểu đích phù hợp |

Không dùng `new E[n]` hoặc một phép ép `Object[]` sang `E[]` như giải pháp lưu trữ mặc định. `List<E>` giúp ví dụ tránh yêu cầu tạo mảng có kiểu thành phần không reifiable.

## 12. Thực hành tự kiểm tra

### Bài 1: Chọn vị trí khai báo kiểu

Một lớp cần giữ `value` qua nhiều lần gọi và trả lại đúng kiểu đó. Nên dùng `class Box<T>` hay chỉ thêm `<T>` cho từng phương thức riêng?

**Đáp án:** tham số kiểu ở cấp lớp giúp giữ cùng một `T` cho trạng thái của đối tượng. Các phương thức generic riêng có tham số kiểu độc lập không tự thiết lập quan hệ đó.

### Bài 2: Nhận nguồn linh hoạt

`Batch<Number>` cần thêm dữ liệu từ `List<Integer>`. Tham số `addAll` nên là `Collection<Number>` hay `Collection<? extends Number>`?

**Đáp án:** `Collection<? extends Number>` mô tả nguồn cung cấp số. Trong lớp generic, chữ ký tương ứng là `Collection<? extends E>`.

### Bài 3: Trả dữ liệu ra ngoài

Tại sao `return items;` làm suy yếu chính sách cấm `null`?

**Đáp án:** người gọi có thể thêm `null` trực tiếp vào danh sách nội bộ mà không qua `add` hoặc `addAll`. Snapshot không cho sửa cấu trúc ngăn đường thay đổi này.

### Bài 4: final có làm StringBuilder bên trong bất biến không?

**Đáp án:** không. Tham chiếu trường ổn định không khóa trạng thái của đối tượng phần tử. Nếu cần bất biến sâu, phải thiết kế chính sách riêng.

### Bài 5: Đổi Batch<Integer> thành Batch<Number>

Có nên ép kiểu để dùng chung một đối tượng dưới hai kiểu đó không?

**Đáp án:** không. Tạo một `Batch<Number>` mới từ nguồn số nguyên nếu muốn thêm được nhiều kiểu số, như chương trình minh họa. Điều đó giữ `Batch<Integer>` gốc không bị đưa phần tử khác kiểu vào.

Một lớp chứa generic có ích khi kiểu dữ liệu và quy tắc sở hữu đi cùng nhau: cùng một tham số kiểu được giữ xuyên suốt lưu trữ, mọi đường ghi bảo vệ các quy tắc của lớp, còn dữ liệu đưa ra ngoài có hợp đồng thay đổi rõ ràng.
